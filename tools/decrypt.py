import base64
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend
import json
import os


KEY = "CLp+L/Tr1MHFlpANE245czmTDsS7a9YRuck3cJ02FTI="


def encrypt_exim_data(data):
    try:
        key = base64.b64decode(KEY)
        iv = os.urandom(16)
        
        json_str = json.dumps(data)
        plaintext = json_str.encode('utf-8')
        
        padder = padding.PKCS7(128).padder()
        padded_plaintext = padder.update(plaintext) + padder.finalize()
        
        cipher = Cipher(
            algorithms.AES(key),
            modes.CBC(iv),
            backend=default_backend()
        )
        
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(padded_plaintext) + encryptor.finalize()
        
        iv_b64 = base64.b64encode(iv).decode('utf-8')
        ciphertext_b64 = base64.b64encode(ciphertext).decode('utf-8')
        
        return f"{iv_b64}:{ciphertext_b64}"
        
    except Exception as e:
        print(f"Encryption failed: {str(e)}")
        return None

    
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
