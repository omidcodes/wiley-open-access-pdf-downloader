import hashlib


def hashify(input):
    in_bytes = input.encode('utf-8') 
    hash_object = hashlib.sha256(in_bytes)
    # Get the hexadecimal representation of the hash
    password_hash = hash_object.hexdigest()
    

    return password_hash