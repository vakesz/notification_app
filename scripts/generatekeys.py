"""# generate_vapid_keys.py"""

import base64

from cryptography.hazmat.primitives.asymmetric import ec

if __name__ == "__main__":
    print("Generating VAPID keys...")
    # Generate private key
    private_key = ec.generate_private_key(ec.SECP256R1())

    # Serialize private key to bytes
    private_value = private_key.private_numbers().private_value
    private_bytes = private_value.to_bytes(32, "big")
    private_key_b64 = base64.urlsafe_b64encode(private_bytes).rstrip(b"=").decode("utf-8")

    # Generate public key
    public_key = private_key.public_key()
    public_numbers = public_key.public_numbers()
    x = public_numbers.x.to_bytes(32, "big")
    y = public_numbers.y.to_bytes(32, "big")
    public_bytes = b"\x04" + x + y
    public_key_b64 = base64.urlsafe_b64encode(public_bytes).rstrip(b"=").decode("utf-8")

    # Output
    print("VAPID Public Key: ", public_key_b64)
    print("VAPID Private Key:", private_key_b64)
