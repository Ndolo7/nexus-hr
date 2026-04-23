import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.db_models import ERPSyncCheckpoint, ERPWebhookEvent
from app.services.erp_client import ERPClientError, erp_client

logger = logging.getLogger(__name__)
engine = create_engine(settings.DATABASE_URL)


class ERPNextSyncService:
    SUPPORTED_DOCTYPES = ("Employee", "Attendance", "Leave Application", "Salary Slip")

    DOCTYPE_FIELDS: Dict[str, List[str]] = {
        "Employee": [
            "name",
            "employee",
            "employee_name",
            "company",
            "department",
            "designation",
            "status",
            "date_of_joining",
            "modified",
        ],
        "Attendance": [
            "name",
            "employee",
            "attendance_date",
            "status",
            "working_hours",
            "modified",
        ],
        "Leave Application": [
            "name",
            "employee",
            "leave_type",
            "from_date",
            "to_date",
            "status",
            "docstatus",
            "modified",
        ],
        "Salary Slip": [
            "name",
            "employee",
            "start_date",
            "end_date",
            "currency",
            "gross_pay",
            "net_pay",
            "docstatus",
            "modified",
        ],
    }

    def _validate_doctype(self, doctype: str) -> None:
        if doctype not in self.SUPPORTED_DOCTYPES:
            raise ValueError(
                f"Unsupported DocType '{doctype}'. Supported DocTypes: {', '.join(self.SUPPORTED_DOCTYPES)}"
            )

    def _get_checkpoint(self, session: Session, doctype: str) -> Optional[ERPSyncCheckpoint]:
        return session.query(ERPSyncCheckpoint).filter(ERPSyncCheckpoint.doctype == doctype).one_or_none()

    def _upsert_checkpoint(self, session: Session, doctype: str, last_modified: Optional[str]) -> ERPSyncCheckpoint:
        checkpoint = self._get_checkpoint(session, doctype)
        if not checkpoint:
            checkpoint = ERPSyncCheckpoint(doctype=doctype)
            session.add(checkpoint)

        checkpoint.last_modified = last_modified
        checkpoint.last_synced_at = datetime.now(timezone.utc)
        session.commit()
        session.refresh(checkpoint)
        return checkpoint

    @staticmethod
    def _max_modified(records: List[Dict[str, Any]]) -> Optional[str]:
        values = [r.get("modified") for r in records if r.get("modified")]
        return max(values) if values else None

    @staticmethod
    def _build_filters(
        modified_after: Optional[str],
        base_filters: Optional[List[Any] | Dict[str, Any]],
    ) -> Optional[List[Any] | Dict[str, Any]]:
        if modified_after:
            if not base_filters:
                return [["modified", ">", modified_after]]
            if isinstance(base_filters, list):
                return [*base_filters, ["modified", ">", modified_after]]
            if isinstance(base_filters, dict):
                result = dict(base_filters)
                result["modified"] = [">", modified_after]
                return result
        return base_filters

    async def pull_doc_type(
        self,
        doctype: str,
        *,
        modified_after: Optional[str] = None,
        limit: int = 200,
        extra_filters: Optional[List[Any] | Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        self._validate_doctype(doctype)

        checkpoint_modified = None
        with Session(engine) as session:
            checkpoint = self._get_checkpoint(session, doctype)
            if checkpoint:
                checkpoint_modified = checkpoint.last_modified

        effective_modified = modified_after or checkpoint_modified
        filters = self._build_filters(effective_modified, extra_filters)
        fields = self.DOCTYPE_FIELDS[doctype]

        records = await erp_client.list_resource(
            doctype,
            filters=filters,
            fields=fields,
            order_by="modified asc",
            limit_page_length=limit,
        )

        latest_modified = self._max_modified(records) or effective_modified
        with Session(engine) as session:
            checkpoint = self._upsert_checkpoint(session, doctype, latest_modified)

        return {
            "doctype": doctype,
            "fetched": len(records),
            "checkpoint": {
                "last_modified": checkpoint.last_modified,
                "last_synced_at": checkpoint.last_synced_at.isoformat() if checkpoint.last_synced_at else None,
            },
            "records": records,
        }

    async def pull_many(
        self,
        doctypes: Optional[List[str]] = None,
        *,
        modified_after: Optional[str] = None,
        limit_per_doctype: int = 200,
    ) -> Dict[str, Any]:
        target_doctypes = doctypes or list(self.SUPPORTED_DOCTYPES)
        results = []

        for doctype in target_doctypes:
            item = await self.pull_doc_type(
                doctype,
                modified_after=modified_after,
                limit=limit_per_doctype,
            )
            results.append(item)

        return {
            "doctypes": target_doctypes,
            "total_records": sum(item["fetched"] for item in results),
            "results": results,
        }

    def list_checkpoints(self) -> List[Dict[str, Any]]:
        with Session(engine) as session:
            rows = session.query(ERPSyncCheckpoint).order_by(ERPSyncCheckpoint.doctype.asc()).all()
            return [
                {
                    "doctype": row.doctype,
                    "last_modified": row.last_modified,
                    "last_synced_at": row.last_synced_at.isoformat() if row.last_synced_at else None,
                }
                for row in rows
            ]

    async def ingest_webhook(self, payload: Dict[str, Any], signature_valid: bool) -> Dict[str, Any]:
        data_block = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        doctype = payload.get("doctype") or data_block.get("doctype")
        docname = payload.get("name") or payload.get("docname") or data_block.get("name")
        event_type = payload.get("event") or payload.get("event_type")

        with Session(engine) as session:
            event = ERPWebhookEvent(
                event_type=event_type,
                doctype=doctype,
                docname=docname,
                payload=payload,
                signature_valid=signature_valid,
            )
            session.add(event)
            session.commit()
            session.refresh(event)

            event_id = event.id

        sync_result: Optional[Dict[str, Any]] = None

        if doctype in self.SUPPORTED_DOCTYPES and docname:
            try:
                synced_record = await erp_client.get_resource(doctype, docname, fields=self.DOCTYPE_FIELDS[doctype])
                sync_result = {"doctype": doctype, "docname": docname, "record": synced_record}

                with Session(engine) as session:
                    latest_modified = synced_record.get("modified")
                    self._upsert_checkpoint(session, doctype, latest_modified)
                    stored_event = session.get(ERPWebhookEvent, event_id)
                    if stored_event:
                        stored_event.status = "processed"
                        session.commit()
            except ERPClientError as exc:
                logger.warning("Webhook sync failed for %s/%s: %s", doctype, docname, exc)
                with Session(engine) as session:
                    stored_event = session.get(ERPWebhookEvent, event_id)
                    if stored_event:
                        stored_event.status = "error"
                        session.commit()

        return {
            "event_id": event_id,
            "doctype": doctype,
            "docname": docname,
            "event_type": event_type,
            "signature_valid": signature_valid,
            "sync_result": sync_result,
        }


erpnext_sync_service = ERPNextSyncService()
