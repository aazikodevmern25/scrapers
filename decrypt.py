import base64
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend
import json


KEY = "CLp+L/Tr1MHFlpANE245czmTDsS7a9YRuck3cJ02FTI="
    
def decrypt_exim_data(encrypted_data):
    try:
        parts = encrypted_data.split(":")
        if len(parts) != 2:
            print(f"Invalid encrypted data format. Expected 'iv:ciphertext', got {len(parts)} parts")
            print(f"Data sample: {encrypted_data[:100]}...")
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
        
        # Try PKCS7 unpadding first
        try:
            unpadder = padding.PKCS7(128).unpadder()
            plaintext = unpadder.update(padded_plaintext) + unpadder.finalize()
        except ValueError as pad_error:
            # If PKCS7 unpadding fails, try manual PKCS7 unpadding
            print(f"PKCS7 unpadding failed: {pad_error}, trying manual PKCS7")
            
            # Manual PKCS7 unpadding: last byte indicates padding length
            padding_length = padded_plaintext[-1]
            
            # Validate padding
            if isinstance(padding_length, int) and 1 <= padding_length <= 16:
                # Check if all padding bytes are the same
                padding_bytes = padded_plaintext[-padding_length:]
                if all(b == padding_length for b in padding_bytes):
                    plaintext = padded_plaintext[:-padding_length]
                    print(f"Successfully removed {padding_length} bytes of padding")
                else:
                    # Invalid padding, try to find JSON end
                    print(f"Invalid padding bytes, searching for JSON end")
                    text = padded_plaintext.decode('utf-8', errors='ignore')
                    # Find the last occurrence of '}'
                    json_end = text.rfind('}')
                    if json_end != -1:
                        plaintext = text[:json_end+1].encode('utf-8')
                    else:
                        plaintext = padded_plaintext
            else:
                print(f"Invalid padding length: {padding_length}, using as-is")
                plaintext = padded_plaintext
        
        plaintext = plaintext.decode('utf-8')
        json_data = json.loads(plaintext)
        return json_data
        
    except Exception as e:
        print(f"Decryption failed: {str(e)}")
        print(f"Error type: {type(e).__name__}")
        if hasattr(e, '__traceback__'):
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
        return None
