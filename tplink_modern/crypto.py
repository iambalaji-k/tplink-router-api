from cryptography.hazmat.primitives.asymmetric import rsa, padding


def rsa_encrypt(password: str, modulus_hex: str, exponent_hex: str) -> str:
    """Encrypt password using RSA public key with PKCS#1 v1.5 padding.

    Args:
        password: Plaintext password string.
        modulus_hex: Hexadecimal string representing the public key modulus.
        exponent_hex: Hexadecimal string representing the public key exponent.

    Returns:
        The ciphertext as a hex-encoded string.
    """
    # Convert hex parameters to integers
    modulus = int(modulus_hex, 16)
    exponent = int(exponent_hex, 16)

    # Create the RSA public key
    public_numbers = rsa.RSAPublicNumbers(exponent, modulus)
    public_key = public_numbers.public_key()

    # Encrypt the password using PKCS#1 v1.5 padding
    ciphertext = public_key.encrypt(
        password.encode("utf-8"),
        padding.PKCS1v15()
    )

    return ciphertext.hex()
