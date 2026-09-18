#!/usr/bin/env python3
import json
import os
from datetime import date, timedelta
from typing import Any

from mcp.server.fastmcp import FastMCP
from zeep import Client
from zeep.helpers import serialize_object
from zeep.transports import Transport

mcp = FastMCP(
    "Tebra SOAP",
    host="0.0.0.0",
    port=int(os.environ.get("PORT", "8000")),
)
_client: Client | None = None

READ_OPERATIONS = {
    "GetAppointment", "GetAppointments", "GetCharges", "GetEncounterDetails",
    "GetPatient", "GetPatients", "GetPayments", "GetPractices",
    "GetProcedureCodes", "GetProviders", "GetServiceLocations", "GetTransactions",
}

def credentials() -> tuple[str, str, str]:
    names = ("TEBRA_USERNAME", "TEBRA_PASSWORD", "TEBRA_CUSTOMER_KEY")
    vals = tuple(os.environ.get(n, "").strip() for n in names)
    missing = [n for n, v in zip(names, vals) if not v]
    if missing:
        raise RuntimeError("Tebra credentials are not configured: " + ", ".join(missing))
    return vals

def client() -> Client:
    global _client
    if _client is None:
        wsdl = os.environ.get("TEBRA_WSDL_URL", "https://webservice.kareo.com/services/soap/2.1/KareoServices.svc?wsdl")
        _client = Client(wsdl=wsdl, transport=Transport(timeout=30, operation_timeout=60))
    return _client

def header() -> dict[str, str]:
    user, password, customer_key = credentials()
    return {"User": user, "Password": password, "CustomerKey": customer_key}

def clean(value: Any, limit: int = 100) -> Any:
    value = serialize_object(value)
    if isinstance(value, list):
        return [clean(v, limit) for v in value[:limit]]
    if isinstance(value, dict):
        return {str(k): clean(v, limit) for k, v in value.items() if v is not None}
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value

def call(operation: str, request: dict[str, Any], limit: int = 100) -> Any:
    request = dict(request or {})
    request["RequestHeader"] = header()
    fn = getattr(client().service, operation)
    return clean(fn(request=request), limit=limit)

@mcp.tool()
def tebra_connection_status() -> dict[str, Any]:
    """Check configuration and load the Tebra WSDL without returning credentials."""
    configured = all(os.environ.get(n) for n in ("TEBRA_USERNAME", "TEBRA_PASSWORD", "TEBRA_CUSTOMER_KEY"))
    result: dict[str, Any] = {"configured": configured, "wsdl": os.environ.get("TEBRA_WSDL_URL", "default")}
    if configured:
        result["available_operations"] = len(list_tebra_operations())
    return result

@mcp.tool()
def list_tebra_operations() -> list[str]:
    """List SOAP operations advertised by the configured Tebra WSDL."""
    operations: set[str] = set()
    for service in client().wsdl.services.values():
        for port in service.ports.values():
            operations.update(port.binding._operations.keys())
    return sorted(operations)

@mcp.tool()
def describe_tebra_operation(operation: str) -> str:
    """Show the WSDL signature for a Tebra SOAP operation before calling it."""
    for service in client().wsdl.services.values():
        for port in service.ports.values():
            op = port.binding._operations.get(operation)
            if op:
                return f"input: {op.input.signature()}\noutput: {op.output.signature()}"
    raise ValueError(f"Unknown Tebra operation: {operation}")

@mcp.tool()
def call_tebra_read_operation(operation: str, request_json: str = "{}", result_limit: int = 100) -> Any:
    """Call an allow-listed read-only Tebra SOAP operation. Use describe_tebra_operation first. request_json omits RequestHeader."""
    if operation not in READ_OPERATIONS:
        raise ValueError(f"Operation is not in the read-only allowlist: {operation}")
    request = json.loads(request_json or "{}")
    if not isinstance(request, dict):
        raise ValueError("request_json must contain a JSON object")
    return call(operation, request, max(1, min(result_limit, 500)))

@mcp.tool()
def upcoming_appointments(days: int = 7, result_limit: int = 100) -> Any:
    """Return Tebra appointments from today through the requested number of days."""
    start = date.today()
    end = start + timedelta(days=max(0, min(days, 90)))
    request = {
        "Filter": {"StartDate": start.isoformat(), "EndDate": end.isoformat()},
        "Fields": {
            "ID": True, "StartDate": True, "EndDate": True, "AppointmentDuration": True,
            "PatientID": True, "PatientFullName": True, "ResourceID1": True,
            "ResourceName1": True, "ConfirmationStatus": True, "ServiceLocationName": True,
            "AppointmentReason1": True, "Type": True, "Notes": True,
        },
    }
    return call("GetAppointments", request, max(1, min(result_limit, 500)))

@mcp.tool()
def find_patients(last_name: str = "", first_name: str = "", date_of_birth: str = "", result_limit: int = 50) -> Any:
    """Find Tebra patients by name and optional DOB in YYYY-MM-DD format."""
    filt = {k: v for k, v in {
        "LastName": last_name, "FirstName": first_name,
        "FromDateOfBirth": date_of_birth, "ToDateOfBirth": date_of_birth,
    }.items() if v}
    request = {
        "Filter": filt,
        "Fields": {
            "ID": True, "PatientFullName": True, "FirstName": True,
            "LastName": True, "DOB": True, "Active": True, "MedicalRecordNumber": True,
        },
    }
    return call("GetPatients", request, max(1, min(result_limit, 500)))

@mcp.tool()
def list_providers(result_limit: int = 100) -> Any:
    """List active providers available to the configured Tebra API account."""
    request = {
        "Filter": {},
        "Fields": {"ID": True, "FullName": True, "FirstName": True, "LastName": True,
                   "Active": True, "PracticeID": True, "PracticeName": True, "Type": True},
    }
    return call("GetProviders", request, max(1, min(result_limit, 500)))

@mcp.tool()
def list_practices(result_limit: int = 50) -> Any:
    """List practices available to the configured Tebra API account."""
    request = {
        "Filter": {},
        "Fields": {"ID": True, "PracticeName": True, "Active": True},
    }
    return call("GetPractices", request, max(1, min(result_limit, 500)))

@mcp.tool()
def create_patient_soap_note(
    patient_id: int,
    patient_name: str,
    note_date: str,
    subjective: str,
    objective: str,
    assessment: str,
    plan: str,
    confirmation_phrase: str = "",
) -> Any:
    """Create a dated SOAP note document in a Tebra patient chart.

    This is a deliberately narrow write operation. First call it without the
    confirmation phrase to preview the exact document. After the user confirms
    the patient and contents, call it again with confirmation_phrase exactly
    equal to CREATE TEBRA NOTE. The patient name is recorded for audit clarity;
    Tebra links the document using patient_id.
    """
    if patient_id <= 0:
        raise ValueError("patient_id must be a positive integer")
    if not patient_name.strip():
        raise ValueError("patient_name is required")
    try:
        parsed_date = date.fromisoformat(note_date)
    except ValueError as exc:
        raise ValueError("note_date must use YYYY-MM-DD format") from exc

    sections = {
        "Subjective": subjective.strip(),
        "Objective": objective.strip(),
        "Assessment": assessment.strip(),
        "Plan": plan.strip(),
    }
    missing = [name for name, value in sections.items() if not value]
    if missing:
        raise ValueError("All SOAP sections are required: " + ", ".join(missing))

    title = f"SOAP Note - {parsed_date.isoformat()}"
    body = "\n".join([
        title,
        f"Patient: {patient_name.strip()} (Tebra Patient ID {patient_id})",
        "",
        *[f"{name}:\n{value}\n" for name, value in sections.items()],
        "This is a system integration test and not a clinical encounter.",
    ])
    preview = {
        "patient_id": patient_id,
        "patient_name": patient_name.strip(),
        "practice_id": 1,
        "document_date": parsed_date.isoformat(),
        "document_name": title,
        "label": "OtherOfficeNote",
        "status": "Processed",
        "file_name": f"soap-note-{parsed_date.isoformat()}.txt",
        "content": body,
    }

    if confirmation_phrase != "CREATE TEBRA NOTE":
        return {
            "created": False,
            "confirmation_required": True,
            "required_confirmation_phrase": "CREATE TEBRA NOTE",
            "preview": preview,
        }

    request = {
        "DocumentToCreate": {
            "DocumentDate": parsed_date.isoformat(),
            "DocumentNotes": "Created through the ChatGPT-Tebra SOAP connector.",
            "FileContent": body.encode("utf-8"),
            "FileName": preview["file_name"],
            "Label": preview["label"],
            "Name": title,
            "PatientId": patient_id,
            "PracticeId": 1,
            "Status": preview["status"],
        }
    }
    response = call("CreateDocument", request)
    return {"created": True, "document": preview, "tebra_response": response}

if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    mcp.run(transport=transport)
