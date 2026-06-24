import hashlib
import hmac
import secrets

def generate_seed(length=32):
    """Genera una semilla criptográficamente segura en formato hexadecimal."""
    return secrets.token_hex(length)

def hash_server_seed(server_seed: str) -> str:
    """Genera el hash SHA-256 de la semilla del servidor para mostrarlo al usuario de forma segura."""
    return hashlib.sha256(server_seed.encode('utf-8')).hexdigest()

def generate_hmac_hash(server_seed: str, client_seed: str, nonce: int, cursor: int = 0) -> bytes:
    """
    Genera el hash HMAC-SHA512 usando la semilla del servidor como clave,
    y una combinación de la semilla del cliente, el nonce y el cursor como mensaje.
    """
    message = f"{client_seed}:{nonce}:{cursor}"
    return hmac.new(
        key=server_seed.encode('utf-8'),
        msg=message.encode('utf-8'),
        digestmod=hashlib.sha512
    ).digest()

def get_uniform_float(server_seed: str, client_seed: str, nonce: int, cursor: int = 0) -> float:
    """
    Genera un número flotante uniforme en el rango [0, 1) extrayendo 52 bits de entropía.
    Ideal para porcentajes, multiplicadores continuos o juegos de Crash.
    """
    digest = generate_hmac_hash(server_seed, client_seed, nonce, cursor)
    
    # Tomamos los primeros 7 bytes (56 bits) para extraer los 52 bits
    # Convertimos los primeros 7 bytes a entero
    value = int.from_bytes(digest[:7], byteorder='big')
    
    # Aplicamos máscara para quedarnos solo con 52 bits
    value = value & ((1 << 52) - 1)
    
    # Dividimos entre 2^52
    return value / (1 << 52)

def get_uniform_integer(server_seed: str, client_seed: str, nonce: int, max_exclusive: int, cursor: int = 0) -> tuple[int, int]:
    """
    Usa Muestreo de Rechazo (Rejection Sampling) para obtener un número entero 
    uniforme en el rango [0, max_exclusive - 1] eliminando el sesgo del módulo.
    
    Retorna una tupla: (resultado, nuevo_cursor).
    El nuevo_cursor debe ser guardado si se necesitan múltiples extracciones en la misma ronda.
    """
    # Usamos enteros de 32 bits para el rechazo
    MAX_UINT32 = (1 << 32) - 1
    limit = MAX_UINT32 - (MAX_UINT32 % max_exclusive)
    
    while True:
        digest = generate_hmac_hash(server_seed, client_seed, nonce, cursor)
        
        # Un hash SHA-512 (64 bytes) nos da 16 enteros de 32 bits por cada digest.
        # Iteramos sobre ellos para no desperdiciar entropía.
        for i in range(16):
            chunk = digest[i*4 : (i+1)*4]
            value = int.from_bytes(chunk, byteorder='big')
            
            if value < limit:
                return value % max_exclusive, cursor + 1
                
        cursor += 1

def generate_provably_fair_result(server_seed: str, client_seed: str, nonce: int, count: int, max_exclusive: int) -> list[int]:
    """
    Genera una lista de 'count' resultados uniformes independientes en el rango [0, max_exclusive - 1].
    Ideal para tirar N dados, extraer N cartas (con reemplazo), etc.
    """
    results = []
    cursor = 0
    for _ in range(count):
        res, cursor = get_uniform_integer(server_seed, client_seed, nonce, max_exclusive, cursor)
        results.append(res)
    return results
