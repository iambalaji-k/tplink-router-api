from tplink_modern.crypto import rsa_encrypt
from tplink_modern.exceptions import AuthenticationError
from tplink_modern.session import RouterSession


class Authenticator:
    def __init__(self, session: RouterSession):
        self.session = session

    async def login(self, password: str) -> str:
        """Perform the login handshake with the router.
        
        Args:
            password: The cleartext administration password.
            
        Returns:
            The retrieved stok session token.
            
        Raises:
            AuthenticationError: If any step of the login fails.
        """
        # Step 1: Query form=keys to get the 1024-bit RSA public key
        try:
            keys_resp = await self.session.post(
                "login?form=keys",
                {"operation": "read"},
                use_login_stok=True
            )
        except Exception as e:
            raise AuthenticationError(f"Failed to fetch encryption keys: {e}") from e

        if not keys_resp.get("success"):
            raise AuthenticationError(f"Failed fetching keys: {keys_resp.get('errorcode', 'unknown error')}")

        try:
            pwd_key = keys_resp["data"]["password"]
            modulus_hex = pwd_key[0]
            exponent_hex = pwd_key[1]
        except (KeyError, IndexError, TypeError) as e:
            raise AuthenticationError(f"Invalid key format returned by router: {e}") from e

        # Step 2: Query form=auth to initialize the login sequence (simulating browser)
        try:
            auth_resp = await self.session.post(
                "login?form=auth",
                {"operation": "read"},
                use_login_stok=True
            )
        except Exception as e:
            raise AuthenticationError(f"Failed to fetch auth sequence: {e}") from e

        if not auth_resp.get("success"):
            raise AuthenticationError(f"Failed fetching auth sequence: {auth_resp.get('errorcode', 'unknown error')}")

        # Step 3: Encrypt the cleartext password using the retrieved keys
        try:
            encrypted_password = rsa_encrypt(password, modulus_hex, exponent_hex)
        except Exception as e:
            raise AuthenticationError(f"Password encryption failed: {e}") from e

        # Step 4: Perform the actual login request
        login_data = {
            "operation": "login",
            "password": encrypted_password
        }
        try:
            login_resp = await self.session.post(
                "login?form=login",
                login_data,
                use_login_stok=True
            )
        except Exception as e:
            raise AuthenticationError(f"Login POST request failed: {e}") from e

        if not login_resp.get("success"):
            err_code = login_resp.get("errorcode", "unknown error")
            raise AuthenticationError(f"Authentication failed: router returned error {err_code}")

        try:
            stok = login_resp["data"]["stok"]
        except (KeyError, TypeError) as e:
            raise AuthenticationError(f"Failed to extract stok from login response: {e}") from e

        # Store the token in the session for subsequent requests
        self.session.stok = stok
        self.session.generation += 1
        return stok
