"""Idempotent OCI Always Free A1 capacity provisioner.

One invocation checks the configured home region's availability domains once.
GitHub Actions provides the periodic scheduling; this process intentionally
does not sleep for an hour or run overlapping launch loops.
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from typing import Iterable

import oci
from oci.exceptions import ServiceError


LOG = logging.getLogger("carsqatar-oci-a1")


@dataclass(frozen=True)
class Settings:
    user: str
    tenancy: str
    compartment: str
    fingerprint: str
    private_key: str
    region: str
    subnet_id: str
    image_id: str
    public_ssh_key: str
    display_name: str = "carsqatar-prod-01"
    ocpus: float = 2
    memory_in_gbs: float = 12
    boot_volume_size_in_gbs: int = 50

    @classmethod
    def from_env(cls) -> "Settings":
        def required(name: str) -> str:
            value = os.getenv(name, "").strip()
            if not value:
                raise ValueError(f"Missing required environment variable: {name}")
            return value

        return cls(
            user=required("OCI_USER_ID"),
            tenancy=required("OCI_TENANCY_ID"),
            compartment=os.getenv("OCI_COMPARTMENT_ID", "").strip()
            or required("OCI_TENANCY_ID"),
            fingerprint=required("OCI_FINGERPRINT"),
            private_key=required("OCI_PRIVATE_KEY"),
            region=os.getenv("OCI_REGION", "").strip() or "uk-london-1",
            subnet_id=required("OCI_SUBNET_ID"),
            image_id=required("OCI_IMAGE_ID"),
            public_ssh_key=required("OCI_PUBLIC_SSH_KEY"),
            display_name=os.getenv("OCI_DISPLAY_NAME", "carsqatar-prod-01").strip(),
        )


def oci_config(settings: Settings) -> dict[str, str]:
    config = {
        "user": settings.user,
        "tenancy": settings.tenancy,
        "fingerprint": settings.fingerprint,
        "key_content": settings.private_key,
        "region": settings.region,
    }
    oci.config.validate_config(config)
    return config


def capacity_error(error: ServiceError) -> bool:
    message = str(error).lower()
    return error.status in {429, 500, 503} and any(
        phrase in message
        for phrase in (
            "out of host capacity",
            "out of capacity",
            "capacity temporarily unavailable",
            "try again later",
        )
    )


def existing_instance(compute_client: object, settings: Settings) -> bool:
    """Return true for any non-terminated instance with our display name."""
    response = compute_client.list_instances(
        compartment_id=settings.compartment,
        display_name=settings.display_name,
    )
    for instance in response.data:
        state = str(getattr(instance, "lifecycle_state", "")).upper()
        if state not in {"TERMINATED", "TERMINATING"}:
            LOG.info("Existing instance found: %s (%s)", instance.id, state)
            return True
    return False


def availability_domains(identity_client: object, settings: Settings) -> list[str]:
    domains = identity_client.list_availability_domains(settings.compartment).data
    return [domain.name for domain in domains]


def launch_details(settings: Settings, availability_domain: str) -> object:
    return oci.core.models.LaunchInstanceDetails(
        display_name=settings.display_name,
        compartment_id=settings.compartment,
        availability_domain=availability_domain,
        shape="VM.Standard.A1.Flex",
        shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(
            ocpus=settings.ocpus,
            memory_in_gbs=settings.memory_in_gbs,
        ),
        source_details=oci.core.models.InstanceSourceViaImageDetails(
            source_type="image",
            image_id=settings.image_id,
            boot_volume_size_in_gbs=settings.boot_volume_size_in_gbs,
        ),
        create_vnic_details=oci.core.models.CreateVnicDetails(
            subnet_id=settings.subnet_id,
            assign_public_ip=True,
            assign_private_dns_record=True,
        ),
        metadata={"ssh_authorized_keys": settings.public_ssh_key},
    )


def provision(settings: Settings, compute_client: object, identity_client: object) -> int:
    if existing_instance(compute_client, settings):
        LOG.info("Nothing to do; instance is already present.")
        return 0

    domains = availability_domains(identity_client, settings)
    if not domains:
        LOG.error("No availability domains were returned for %s", settings.region)
        return 1

    for domain in domains:
        LOG.info("Trying A1 capacity in %s", domain)
        try:
            response = compute_client.launch_instance(launch_details(settings, domain))
            LOG.info("Launch accepted in %s: %s", domain, response.data.id)
            return 0
        except ServiceError as error:
            if capacity_error(error):
                LOG.warning("A1 capacity unavailable in %s; continuing", domain)
                continue
            LOG.error("OCI rejected the request in %s: %s", domain, error.message)
            return 1

    LOG.info("No A1 capacity was available in any domain; try again next schedule.")
    return 2


def main() -> int:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(levelname)s %(message)s")
    try:
        settings = Settings.from_env()
        config = oci_config(settings)
        compute_client = oci.core.ComputeClient(config)
        identity_client = oci.identity.IdentityClient(config)
        return provision(settings, compute_client, identity_client)
    except (ValueError, oci.exceptions.ConfigFileNotFound, oci.exceptions.InvalidConfig) as error:
        LOG.error("Configuration error: %s", error)
        return 1
    except Exception:
        LOG.exception("Unexpected provisioner failure")
        return 1


if __name__ == "__main__":
    sys.exit(main())
