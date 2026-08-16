import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from src.provision_a1 import Settings, capacity_error, existing_instance, launch_details


class ProvisionerTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(
            user="u", tenancy="t", compartment="c", fingerprint="f",
            private_key="pem", region="uk-london-1", subnet_id="s",
            image_id="i", public_ssh_key="ssh-ed25519 AAAA test",
        )

    def test_capacity_error_is_narrow(self):
        class FakeError:
            def __init__(self, status, message):
                self.status = status
                self.message = message

            def __str__(self):
                return self.message

        self.assertTrue(capacity_error(FakeError(500, "out of host capacity")))
        self.assertFalse(capacity_error(FakeError(401, "out of host capacity")))

    def test_existing_instance_blocks_launch(self):
        client = Mock()
        client.list_instances.return_value = SimpleNamespace(
            data=[SimpleNamespace(id="ocid1.instance", lifecycle_state="RUNNING")]
        )
        self.assertTrue(existing_instance(client, self.settings))

    def test_launch_details_are_current_free_target(self):
        details = launch_details(self.settings, "AD-1")
        self.assertEqual(details.shape, "VM.Standard.A1.Flex")
        self.assertEqual(details.shape_config.ocpus, 2)
        self.assertEqual(details.shape_config.memory_in_gbs, 12)
        self.assertEqual(details.source_details.boot_volume_size_in_gbs, 50)


if __name__ == "__main__":
    unittest.main()
