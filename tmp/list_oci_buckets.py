import os
import oci


cfg = {
    "user": os.getenv("OCI_USER_OCID"),
    "tenancy": os.getenv("OCI_TENANCY_OCID"),
    "fingerprint": os.getenv("OCI_FINGERPRINT"),
    "region": os.getenv("OCI_REGION"),
    "key_file": os.getenv("OCI_KEY_FILE"),
}

client = oci.object_storage.ObjectStorageClient(cfg)
namespace = client.get_namespace().data
compartment_id = os.getenv("OCI_COMPARTMENT_OCID") or os.getenv("OCI_TENANCY_OCID")

print(f"NAMESPACE={namespace}")
for bucket in client.list_buckets(namespace, compartment_id).data:
    print(f"BUCKET={bucket.name}")
