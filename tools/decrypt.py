import base64
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend
import json


KEY = "sIeCk3p6K8Qx9MM2XFl7bw6LdLX2OrUfisVCe/2/mWI="
    
def decrypt_exim_data(encrypted_data):
    try:
        parts = encrypted_data.split(":")
        if len(parts) != 2:
            raise ValueError("Invalid encrypted data format. Expected 'iv:ciphertext'")
        
        iv_b64, ciphertext_b64 = parts
        
        iv = base64.b64decode(iv_b64)
        ciphertext = base64.b64decode(ciphertext_b64)
        key = base64.b64decode(KEY)
        
        # Create cipher
        cipher = Cipher(
            algorithms.AES(key),
            modes.CBC(iv),
            backend=default_backend()
        )
        
        decryptor = cipher.decryptor()
        padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()
        
        unpadder = padding.PKCS7(128).unpadder()
        plaintext = unpadder.update(padded_plaintext) + unpadder.finalize()
        plaintext =  plaintext.decode('utf-8')
        json_data = json.loads(plaintext)
        return json_data
        
    except Exception as e:
        print(f"Decryption failed: {str(e)}")
        return None
