# Cars Qatar OCI A1 provisioner

This repository checks for capacity for one Always Free OCI Ampere A1 instance
in the tenancy's home region and launches it once capacity becomes available.
It is configured for the current Always Free target: `VM.Standard.A1.Flex` with
2 OCPUs, 12 GB RAM, Ubuntu ARM64, and a 50 GB boot volume.

The workflow runs once every five minutes at most. Each run:

1. Checks for an existing non-terminated `carsqatar-prod-01` instance.
2. Discovers the region's availability domains instead of hardcoding AD IDs.
3. Attempts one launch per domain.
4. Retries only capacity-style errors on the next scheduled run.
5. Stops after the first accepted launch, preventing duplicates.

## Required GitHub configuration

Add these repository **Actions secrets**:

| Secret | Value |
| --- | --- |
| `OCI_USER_ID` | OCI user OCID |
| `OCI_PRIVATE_KEY` | Full API signing private key, including PEM lines |
| `OCI_FINGERPRINT` | API key fingerprint |
| `OCI_TENANCY_ID` | Tenancy OCID |
| `OCI_COMPARTMENT_ID` | Root compartment OCID, usually the tenancy OCID |
| `OCI_SUBNET_ID` | OCID of the public subnet in the Cars Qatar VCN |
| `OCI_IMAGE_ID` | Ubuntu 24.04 ARM64 image OCID for `uk-london-1` |
| `OCI_PUBLIC_SSH_KEY` | The public key installed in the instance |

Add this repository **Actions variable**:

| Variable | Value |
| --- | --- |
| `OCI_REGION` | `uk-london-1` |

Do not commit OCI API keys, SSH private keys, OCIDs in private context, or
`.env` files. Use the workflow's manual **Run workflow** button for the first
test. The scheduled workflow may be delayed by GitHub and does not guarantee
capacity.

## Safety notes

- This does not create the E2 micro and does not delete or resize any instance.
- It assumes the supplied image is ARM64 and Always Free eligible.
- It uses the account's current Always Free target of 2 OCPUs and 12 GB RAM;
  it intentionally does not request the old 4 OCPU/24 GB configuration.
- A capacity check is not a reservation. OCI may reject a launch after the
  check, so the create call remains the final authority.
