from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class TelemetryReport(BaseModel):
    hostname: str
    ip_address: Optional[str] = None
    cpu: Optional[float] = None
    load: Optional[List[float]] = None
    mem: Optional[Dict[str, Any]] = None
    swap: Optional[Dict[str, Any]] = None
    disk: Optional[Any] = None
    net: Optional[Any] = None
    uptime: Optional[int] = None
    procs: Optional[int] = None
    top_procs: Optional[Any] = None
    systemd_units: Optional[Any] = None
    services: Optional[Any] = None
    accounts: Optional[Any] = None
    security: Optional[Any] = None
    firewall: Optional[Any] = None
    listening_ports: Optional[Any] = None
    cron_jobs: Optional[Any] = None
    ssl_certs: Optional[Any] = None
    hardware: Optional[Any] = None
    kernel: Optional[str] = None
    os: Optional[str] = None
    arch: Optional[str] = None
    agent_version: Optional[str] = None
    apt: Optional[Any] = None
    fim: Optional[Any] = None
    kernel_events: Optional[Any] = None

    class Config:
        extra = "allow"
