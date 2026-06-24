"""
Módulo para manejar los niveles de los trabajos.
Este módulo extiende la funcionalidad del sistema de economía
añadiendo niveles de trabajo que aumentan las recompensas y capacidades.
"""

import discord
from src.db import get_connection

# Constantes para el sistema de niveles
MAX_NIVEL = 10
XP_BASE = 100  # XP base necesaria para subir al nivel 1
FACTOR_XP = 1.5  # Factor multiplicador de XP por nivel

# Tipos de trabajo
TIPOS_TRABAJO = {
    'hacker': {
        'nombre': 'Hacker',
        'emoji': '💻',
        'color': discord.Color.blue(),
        'descripcion': 'Descifra códigos y sistemas informáticos',
        'energia_base': 25,  # Energía base requerida
        'recompensa_base': 300,  # Recompensa base promedio
        'tier_economico': '⭐⭐⭐ (Medio-Alto)',
        'riesgo': '⭐⭐ (Medio)',
        'xp_por_trabajo': 15,  # XP base por trabajo completado
        'bonificaciones': {
            # nivel: {bonificación}
            1: 'Acceso a tareas básicas',
            2: '+10% recompensa base',
            3: '-5% energía requerida',
            4: '+15% recompensa base',
            5: 'Bypass Cortafuegos (+95% Hackear)',
            6: '+20% recompensa base',
            7: '-10% energía requerida',
            8: 'Inyección SQL (Muestra bits/paridad)',
            9: 'Desbloquea tareas maestras',
            10: '+50% recompensa, -15% energía'
        }
    },
    'chef': {
        'nombre': 'Chef',
        'emoji': '👨‍🍳',
        'color': discord.Color.orange(),
        'descripcion': 'Prepara platos exquisitos',
        'energia_base': 20,
        'recompensa_base': 200,
        'tier_economico': '⭐⭐ (Medio)',
        'riesgo': '⭐⭐ (Medio)',
        'xp_por_trabajo': 12,
        'bonificaciones': {
            1: 'Acceso a recetas básicas',
            2: '+10% recompensa base',
            3: '-5% energía requerida',
            4: '+15% recompensa base',
            5: 'Ingrediente Secreto (+30% monedas)',
            6: '+20% recompensa base',
            7: '-10% energía requerida',
            8: 'Ajuste de Temperatura (Control de cocción)',
            9: 'Desbloquea recetas maestras',
            10: '+50% recompensa, -15% energía'
        }
    },
    'artista': {
        'nombre': 'Artista',
        'emoji': '🎨',
        'color': discord.Color.purple(),
        'descripcion': 'Crea obras de arte únicas',
        'energia_base': 15,
        'recompensa_base': 150,
        'tier_economico': '⭐ (Bajo)',
        'riesgo': '⭐ (Bajo)',
        'xp_por_trabajo': 10,
        'bonificaciones': {
            1: 'Acceso a obras básicas',
            2: '+10% recompensa base',
            3: '-5% energía requerida',
            4: '+15% recompensa base',
            5: 'Estilo de Obra (Bonos personalizados)',
            6: '+20% recompensa base',
            7: '-10% energía requerida',
            8: 'Subasta de Arte (Venta de alto riesgo)',
            9: 'Desbloquea obras maestras',
            10: '+50% recompensa, -15% energía'
        }
    },
    'mecanico': {
        'nombre': 'Mecánico',
        'emoji': '🔧',
        'color': discord.Color.dark_gray(),
        'descripcion': 'Repara y mejora vehículos',
        'energia_base': 30,
        'recompensa_base': 350,
        'tier_economico': '⭐⭐⭐⭐ (Alto)',
        'riesgo': '⭐⭐ (Medio)',
        'xp_por_trabajo': 20,
        'bonificaciones': {
            1: 'Acceso a reparaciones básicas',
            2: '+10% recompensa base',
            3: '-5% energía requerida',
            4: '+15% recompensa base',
            5: 'Escáner OBD (Elimina falsos diagnósticos)',
            6: '+20% recompensa base',
            7: '-10% energía requerida',
            8: 'Diagnóstico Avanzado (Detección instantánea)',
            9: 'Desbloquea reparaciones maestras',
            10: '+50% recompensa, -15% energía'
        }
    },
    'minero': {
        'nombre': 'Minero',
        'emoji': '⛏️',
        'color': discord.Color.gold(),
        'descripcion': 'Excava en túneles buscando gemas y metales',
        'energia_base': 25,
        'recompensa_base': 300,
        'tier_economico': '⭐⭐⭐ (Medio-Alto)',
        'riesgo': '⭐⭐⭐ (Alto)',
        'xp_por_trabajo': 15,
        'bonificaciones': {
            1: 'Acceso a túneles básicos',
            2: '+10% recompensa base',
            3: '-5% energía requerida',
            4: '+15% recompensa base',
            5: 'Vigas de Soporte (+30% estabilidad)',
            6: '+20% recompensa base',
            7: '-10% energía requerida',
            8: 'Carga Dinamita C4 (Extracción rápida)',
            9: 'Desbloquea túneles maestros',
            10: '+50% recompensa, -15% energía'
        }
    },
    'pescador': {
        'nombre': 'Pescador',
        'emoji': '🎣',
        'color': discord.Color.teal(),
        'descripcion': 'Pesca criaturas y monstruos en lagos y océanos',
        'energia_base': 20,
        'recompensa_base': 220,
        'tier_economico': '⭐⭐ (Medio)',
        'riesgo': '⭐⭐⭐ (Alto)',
        'xp_por_trabajo': 12,
        'bonificaciones': {
            1: 'Acceso a zonas de pesca básicas',
            2: '+10% recompensa base',
            3: '-5% energía requerida',
            4: '+15% recompensa base',
            5: 'Cebo Premium (+15% zona segura)',
            6: '+20% recompensa base',
            7: '-10% energía requerida',
            8: 'Red de Pesca de Arrastre (Sin riesgo)',
            9: 'Desbloquea profundidades abisales',
            10: '+50% recompensa, -15% energía'
        }
    },
    'piloto': {
        'nombre': 'Piloto',
        'emoji': '✈️',
        'color': discord.Color.light_grey(),
        'descripcion': 'Pilota vuelos comerciales y de contrabando',
        'energia_base': 40,
        'recompensa_base': 500,
        'tier_economico': '⭐⭐⭐⭐⭐ (Muy Alto)',
        'riesgo': '⭐⭐⭐ (Alto)',
        'xp_por_trabajo': 25,
        'bonificaciones': {
            1: 'Licencia de Vuelo Básica',
            2: '+10% recompensa base',
            3: '-5% energía requerida',
            4: '+15% recompensa base',
            5: 'Radar Meteorológico (Evita 1 tormenta)',
            6: '+20% recompensa base',
            7: '-10% energía requerida',
            8: 'Motor Turbohélice (Aumenta márgen de tiempo)',
            9: 'Licencia de Contrabando',
            10: '+50% recompensa, -15% energía'
        }
    },
    'cazarrecompensas': {
        'nombre': 'Cazarrecompensas',
        'emoji': '🗡️',
        'color': discord.Color.dark_red(),
        'descripcion': 'Busca fugitivos para cobrar su cabeza',
        'energia_base': 35,
        'recompensa_base': 400,
        'tier_economico': '⭐⭐⭐⭐ (Alto)',
        'riesgo': '⭐⭐⭐ (Alto)',
        'xp_por_trabajo': 22,
        'bonificaciones': {
            1: 'Cazarrecompensas Novato',
            2: '+10% recompensa base',
            3: '-5% energía requerida',
            4: '+15% recompensa base',
            5: 'Gafas Infrarrojas (Revela área descartada)',
            6: '+20% recompensa base',
            7: '-10% energía requerida',
            8: 'Perro Rastreador (Intento Extra)',
            9: 'Objetivos de Alto Valor',
            10: '+50% recompensa, -15% energía'
        }
    },
    'medico': {
        'nombre': 'Médico',
        'emoji': '⚕️',
        'color': discord.Color.red(),
        'descripcion': 'Realiza cirugías complejas bajo presión',
        'energia_base': 25,
        'recompensa_base': 300,
        'tier_economico': '⭐⭐⭐ (Medio-Alto)',
        'riesgo': '⭐⭐⭐ (Alto)',
        'xp_por_trabajo': 15,
        'bonificaciones': {
            1: 'Residente',
            2: '+10% recompensa base',
            3: '-5% energía requerida',
            4: '+15% recompensa base',
            5: 'Anestesia Mejorada (Tiempo extra)',
            6: '+20% recompensa base',
            7: '-10% energía requerida',
            8: 'Bisturí Láser (No puedes fallar)',
            9: 'Jefe de Cirugía',
            10: '+50% recompensa, -15% energía'
        }
    },
    'ladron': {
        'nombre': 'Ladrón',
        'emoji': '🥷',
        'color': discord.Color.dark_theme(),
        'descripcion': 'Asalta bancos memorizando códigos',
        'energia_base': 30,
        'recompensa_base': 450,
        'tier_economico': '⭐⭐⭐⭐ (Alto)',
        'riesgo': '⭐⭐⭐ (Alto)',
        'xp_por_trabajo': 20,
        'bonificaciones': {
            1: 'Carterista',
            2: '+10% recompensa base',
            3: '-5% energía requerida',
            4: '+15% recompensa base',
            5: 'Ganzúa Electrónica (Falla sin multa 1 vez)',
            6: '+20% recompensa base',
            7: '-10% energía requerida',
            8: 'Penetración de Bóvedas',
            9: 'Fantasma (Robos Imposibles)',
            10: '+50% recompensa, -15% energía'
        }
    },
    'cientifico': {
        'nombre': 'Científico',
        'emoji': '🔬',
        'color': discord.Color.green(),
        'descripcion': 'Mezcla químicos para crear fórmulas',
        'energia_base': 20,
        'recompensa_base': 250,
        'tier_economico': '⭐⭐ (Medio)',
        'riesgo': '⭐⭐ (Medio)',
        'xp_por_trabajo': 12,
        'bonificaciones': {
            1: 'Asistente de Laboratorio',
            2: '+10% recompensa base',
            3: '-5% energía requerida',
            4: '+15% recompensa base',
            5: 'Pipeta de Precisión (No hay químicos falsos)',
            6: '+20% recompensa base',
            7: '-10% energía requerida',
            8: 'Catalizador (Doble producción)',
            9: 'Premio Nobel',
            10: '+50% recompensa, -15% energía'
        }
    }
}

def setup_db():
    """Verifica la base de datos para el sistema de niveles de trabajo en PostgreSQL"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Crear tabla joblevels con restricción de unicidad para ON CONFLICT
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS joblevels (
        ID SERIAL PRIMARY KEY,
        UserId BIGINT,
        JobType VARCHAR(20),
        CompletedJobs INT DEFAULT 0,
        Level INT DEFAULT 0,
        Experience INT DEFAULT 0,
        CreatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UpdatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT uq_userid_jobtype UNIQUE (UserId, JobType)
    )
    """)
    
    # Verificar si necesitamos añadir columnas para el sistema de niveles mejorado
    cursor.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'joblevels'
    """)
    columns = [row[0].lower() for row in cursor.fetchall()]
    
    if 'level' not in columns:
        cursor.execute("ALTER TABLE joblevels ADD COLUMN Level INT DEFAULT 0")
    if 'experience' not in columns:
        cursor.execute("ALTER TABLE joblevels ADD COLUMN Experience INT DEFAULT 0")
    
    conn.commit()
    conn.close()

def get_nivel_trabajo(user_id, tipo_trabajo):
    """Obtiene el nivel de un usuario en un tipo de trabajo específico
    
    Args:
        user_id: ID del usuario
        tipo_trabajo: Tipo de trabajo ('hacker', 'chef', 'artista', 'mecanico')
        
    Returns:
        dict: Diccionario con nivel, experiencia y trabajos_totales
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    # Asegurarse de que existe la entrada para el usuario y tipo de trabajo usando ON CONFLICT
    cursor.execute("""
    INSERT INTO joblevels (UserId, JobType, CompletedJobs, Level, Experience)
    VALUES (%s, %s, 0, 0, 0)
    ON CONFLICT (UserId, JobType) DO NOTHING
    """, (user_id, tipo_trabajo))
    
    # Consultar datos
    cursor.execute("""
    SELECT COALESCE(Level, 0) AS Level, 
           COALESCE(Experience, 0) AS Experience, 
           CompletedJobs
    FROM joblevels
    WHERE UserId = %s AND JobType = %s
    """, (user_id, tipo_trabajo))
    
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            "nivel": row[0],
            "experiencia": row[1],
            "trabajos_totales": row[2]
        }
    else:
        # En caso de algún error, devolver valores predeterminados
        return {
            "nivel": 0,
            "experiencia": 0,
            "trabajos_totales": 0
        }

def add_experiencia_trabajo(user_id, tipo_trabajo, xp_ganada):
    """Añade experiencia a un usuario en un tipo de trabajo específico
    y sube de nivel si corresponde
    
    Args:
        user_id: ID del usuario
        tipo_trabajo: Tipo de trabajo ('hacker', 'chef', 'artista', 'mecanico')
        xp_ganada: Cantidad de experiencia a añadir
        
    Returns:
        dict: Diccionario con nivel_anterior, nivel_nuevo, subio_nivel
    """
    from src.db import usuario_tiene_item, usar_item_usuario
    
    # Verificar Poción de Enfoque (ID 4)
    pocion_usada = False
    if usuario_tiene_item(user_id, 4):
        if usar_item_usuario(user_id, 4):
            xp_ganada = int(xp_ganada * 1.5)
            pocion_usada = True

    # Obtener nivel actual
    datos_nivel = get_nivel_trabajo(user_id, tipo_trabajo)
    nivel_actual = datos_nivel["nivel"]
    xp_actual = datos_nivel["experiencia"]
    
    # Añadir XP
    xp_nueva = xp_actual + xp_ganada
    
    # Calcular si sube de nivel
    subio_nivel = False
    nivel_nuevo = nivel_actual
    
    while nivel_nuevo < MAX_NIVEL:
        xp_necesaria = calcular_xp_necesaria(nivel_nuevo)
        if xp_nueva >= xp_necesaria:
            nivel_nuevo += 1
            xp_nueva -= xp_necesaria
            subio_nivel = True
        else:
            break
    
    # Actualizar en la base de datos
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
    UPDATE joblevels
    SET Level = %s, 
        Experience = %s, 
        CompletedJobs = CompletedJobs + 1, 
        UpdatedAt = CURRENT_TIMESTAMP
    WHERE UserId = %s AND JobType = %s
    """, (nivel_nuevo, xp_nueva, user_id, tipo_trabajo))
    
    conn.commit()
    conn.close()
    
    return {
        "nivel_anterior": nivel_actual,
        "nivel_nuevo": nivel_nuevo,
        "subio_nivel": subio_nivel,
        "xp_actual": xp_nueva,
        "xp_para_siguiente": calcular_xp_necesaria(nivel_nuevo) if nivel_nuevo < MAX_NIVEL else 0,
        "xp_ganada_final": xp_ganada,
        "pocion_usada": pocion_usada
    }

def calcular_xp_necesaria(nivel_actual):
    """Calcula la XP necesaria para subir al siguiente nivel
    
    Args:
        nivel_actual: Nivel actual del usuario
        
    Returns:
        int: XP necesaria para el siguiente nivel
    """
    return int(XP_BASE * (FACTOR_XP ** nivel_actual))

def get_todos_niveles_trabajo(user_id):
    """Obtiene todos los niveles de trabajo de un usuario
    
    Args:
        user_id: ID del usuario
        
    Returns:
        dict: Diccionario con los niveles para cada tipo de trabajo
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    # Consultar todos los trabajos del usuario de una vez
    cursor.execute("""
    SELECT JobType, 
           COALESCE(Level, 0) AS Level, 
           COALESCE(Experience, 0) AS Experience, 
           CompletedJobs
    FROM joblevels
    WHERE UserId = %s
    """, (user_id,))
    
    resultado = {}
    # Inicializar con valores por defecto para todos los tipos de trabajo
    for tipo in TIPOS_TRABAJO.keys():
        resultado[tipo] = {
            "nivel": 0,
            "experiencia": 0,
            "trabajos_totales": 0
        }
    
    # Actualizar con los datos de la base de datos
    for row in cursor.fetchall():
        tipo_trabajo = row[0]
        if tipo_trabajo in resultado:
            resultado[tipo_trabajo] = {
                "nivel": row[1],
                "experiencia": row[2],
                "trabajos_totales": row[3]
            }
    
    conn.close()
    return resultado

def calcular_bonificaciones(user_id, tipo_trabajo):
    """Calcula las bonificaciones aplicadas según el nivel del usuario
    
    Args:
        user_id: ID del usuario
        tipo_trabajo: Tipo de trabajo ('hacker', 'chef', 'artista', 'mecanico')
        
    Returns:
        dict: Bonificaciones aplicadas (recompensa_multiplicador, energia_reduccion)
    """
    nivel_info = get_nivel_trabajo(user_id, tipo_trabajo)
    nivel = nivel_info["nivel"]
    
    # Valores iniciales
    recompensa_multiplicador = 1.0
    energia_reduccion = 0.0
    
    # Aplicar bonificaciones según nivel
    if nivel >= 2:
        recompensa_multiplicador += 0.1
    if nivel >= 3:
        energia_reduccion += 0.05
    if nivel >= 4:
        recompensa_multiplicador += 0.05
    if nivel >= 6:
        recompensa_multiplicador += 0.05
    if nivel >= 7:
        energia_reduccion += 0.05
    if nivel >= 8:
        recompensa_multiplicador += 0.05
    if nivel >= 10:
        recompensa_multiplicador += 0.25
        energia_reduccion += 0.05
    
    return {
        "recompensa_multiplicador": recompensa_multiplicador,
        "energia_reduccion": energia_reduccion
    }

def calcular_energia_requerida(energia_base, user_id, tipo_trabajo):
    """Calcula la energía requerida para un trabajo considerando el nivel
    
    Args:
        energia_base: Energía base requerida por el trabajo
        user_id: ID del usuario
        tipo_trabajo: Tipo de trabajo
        
    Returns:
        int: Energía requerida ajustada por nivel
    """
    bonificaciones = calcular_bonificaciones(user_id, tipo_trabajo)
    energia_reduccion = bonificaciones["energia_reduccion"]
    
    energia_requerida = int(energia_base * (1 - energia_reduccion))
    return max(energia_requerida, 1)  # Mínimo 1 de energía

def calcular_recompensa(recompensa_base, user_id, tipo_trabajo):
    """Calcula la recompensa para un trabajo considerando el nivel
    
    Args:
        recompensa_base: Recompensa base del trabajo
        user_id: ID del usuario
        tipo_trabajo: Tipo de trabajo
        
    Returns:
        int: Recompensa ajustada por nivel
    """
    bonificaciones = calcular_bonificaciones(user_id, tipo_trabajo)
    recompensa_multiplicador = bonificaciones["recompensa_multiplicador"]
    
    return int(recompensa_base * recompensa_multiplicador)

def get_resumen_nivel(user_id, tipo_trabajo):
    """Obtiene un resumen completo del nivel del usuario en un trabajo
    
    Args:
        user_id: ID del usuario
        tipo_trabajo: Tipo de trabajo ('hacker', 'chef', 'artista', 'mecanico')
        
    Returns:
        dict: Diccionario con información completa del nivel
    """
    # Obtener datos básicos
    info_nivel = get_nivel_trabajo(user_id, tipo_trabajo)
    nivel_actual = info_nivel["nivel"]
    xp_actual = info_nivel["experiencia"]
    trabajos_totales = info_nivel["trabajos_totales"]
    
    # Calcular XP para siguiente nivel
    if nivel_actual < MAX_NIVEL:
        xp_necesaria = calcular_xp_necesaria(nivel_actual)
        progreso_porcentaje = (xp_actual / xp_necesaria) * 100 if xp_necesaria > 0 else 100
    else:
        xp_necesaria = 0
        progreso_porcentaje = 100
    
    # Obtener bonificaciones
    bonificaciones = calcular_bonificaciones(user_id, tipo_trabajo)
    info_trabajo = TIPOS_TRABAJO[tipo_trabajo]
    
    # Crear barra de progreso visual
    progreso = min(int(progreso_porcentaje / 10), 10)
    barra_progreso = "█" * progreso + "░" * (10 - progreso)
    
    return {
        "nivel": nivel_actual,
        "xp_actual": xp_actual,
        "xp_necesaria": xp_necesaria,
        "trabajos_totales": trabajos_totales,
        "progreso_porcentaje": progreso_porcentaje,
        "barra_progreso": barra_progreso,
        "recompensa_multiplicador": bonificaciones["recompensa_multiplicador"],
        "energia_reduccion": bonificaciones["energia_reduccion"],
        "bonificacion_actual": info_trabajo['bonificaciones'].get(nivel_actual, "Sin bonificaciones"),
        "bonificacion_siguiente": info_trabajo['bonificaciones'].get(nivel_actual + 1, "Nivel máximo alcanzado") if nivel_actual < MAX_NIVEL else None,
        "es_nivel_maximo": nivel_actual >= MAX_NIVEL,
        "info_trabajo": info_trabajo
    }

def crear_embed_nivel(user_id, tipo_trabajo):
    """Crea un embed para mostrar el nivel en un trabajo específico
    
    Args:
        user_id: ID del usuario
        tipo_trabajo: Tipo de trabajo ('hacker', 'chef', 'artista', 'mecanico')
        
    Returns:
        discord.Embed: Embed con la información del nivel
    """
    # Obtener datos
    resumen = get_resumen_nivel(user_id, tipo_trabajo)
    info_trabajo = TIPOS_TRABAJO[tipo_trabajo]
    
    # Crear embed
    embed = discord.Embed(
        title=f"{info_trabajo['emoji']} Nivel de {info_trabajo['nombre']}",
        description=f"Progreso en el trabajo de {info_trabajo['nombre']}",
        color=info_trabajo['color']
    )
    
    # Información de nivel
    if resumen["es_nivel_maximo"]:
        info_nivel = f"**Nivel {resumen['nivel']}** (Máximo) ✨"
        progreso_texto = "✅ Nivel máximo alcanzado"
    else:
        info_nivel = f"**Nivel {resumen['nivel']}**"
        progreso_texto = f"{resumen['barra_progreso']} {resumen['xp_actual']}/{resumen['xp_necesaria']} XP"
    
    # Añadir campos
    embed.add_field(
        name="📊 Progreso",
        value=f"{info_nivel}\n{progreso_texto}",
        inline=False
    )
    
    embed.add_field(
        name="💼 Experiencia Laboral",
        value=f"👔 **Trabajos completados:** {resumen['trabajos_totales']}\n"
              f"⭐ **Bonificación actual:** {resumen['bonificacion_actual']}\n"
              f"⏭️ **Siguiente nivel:** {resumen['bonificacion_siguiente'] if not resumen['es_nivel_maximo'] else 'N/A'}",
        inline=False
    )
    
    embed.add_field(
        name="🌟 Bonificaciones Activas",
        value=f"💰 **Recompensa:** +{int((resumen['recompensa_multiplicador'] - 1) * 100)}%\n"
              f"⚡ **Reducción de energía:** -{int(resumen['energia_reduccion'] * 100)}%",
        inline=False
    )
    
    return embed

def get_energia_trabajo(tipo_trabajo, user_id=None):
    """Obtiene la energía base requerida para un trabajo
    
    Args:
        tipo_trabajo: Tipo de trabajo ('hacker', 'chef', 'artista', 'mecanico')
        user_id: ID del usuario (opcional, si se proporciona se aplican bonificaciones)
        
    Returns:
        int: Energía requerida
    """
    energia_base = TIPOS_TRABAJO[tipo_trabajo].get('energia_base', 20)
    
    if user_id:
        return calcular_energia_requerida(energia_base, user_id, tipo_trabajo)
    
    return energia_base

def get_recompensa_trabajo(tipo_trabajo, user_id=None):
    """Obtiene la recompensa base para un trabajo
    
    Args:
        tipo_trabajo: Tipo de trabajo ('hacker', 'chef', 'artista', 'mecanico')
        user_id: ID del usuario (opcional, si se proporciona se aplican bonificaciones)
        
    Returns:
        int: Recompensa base
    """
    recompensa_base = TIPOS_TRABAJO[tipo_trabajo].get('recompensa_base', 200)
    
    if user_id:
        return calcular_recompensa(recompensa_base, user_id, tipo_trabajo)
    
    return recompensa_base

def calcular_xp_restante(user_id, tipo_trabajo):
    """Calcula cuánta XP falta para subir al siguiente nivel
    
    Args:
        user_id: ID del usuario
        tipo_trabajo: Tipo de trabajo ('hacker', 'chef', 'artista', 'mecanico')
        
    Returns:
        dict: Diccionario con información sobre XP restante y progreso
    """
    # Obtener nivel actual
    datos_nivel = get_nivel_trabajo(user_id, tipo_trabajo)
    nivel_actual = datos_nivel["nivel"]
    xp_actual = datos_nivel["experiencia"]
    
    # Si ya está en nivel máximo, no hay más progresión
    if nivel_actual >= MAX_NIVEL:
        return {
            "nivel_actual": nivel_actual,
            "xp_actual": xp_actual,
            "xp_necesaria": 0,
            "xp_restante": 0,
            "progreso_porcentaje": 100,
            "es_nivel_maximo": True
        }
    
    # Calcular XP necesaria para el siguiente nivel
    xp_necesaria = calcular_xp_necesaria(nivel_actual)
    xp_restante = xp_necesaria - xp_actual
    progreso_porcentaje = (xp_actual / xp_necesaria) * 100 if xp_necesaria > 0 else 0
    
    return {
        "nivel_actual": nivel_actual,
        "xp_actual": xp_actual,
        "xp_necesaria": xp_necesaria,
        "xp_restante": xp_restante,
        "progreso_porcentaje": progreso_porcentaje,
        "es_nivel_maximo": False
    }

def calcular_trabajos_para_nivel(tipo_trabajo, nivel_actual=0):
    """Calcula aproximadamente cuántos trabajos se necesitan para alcanzar un nivel específico
    
    Args:
        tipo_trabajo: Tipo de trabajo ('hacker', 'chef', 'artista', 'mecanico')
        nivel_actual: Nivel actual del usuario (por defecto 0)
        
    Returns:
        dict: Diccionario con información sobre trabajos necesarios por nivel
    """
    xp_por_trabajo = TIPOS_TRABAJO[tipo_trabajo].get('xp_por_trabajo', 10)
    trabajos_por_nivel = {}
    xp_acumulada = 0
    
    # Calcular para todos los niveles o hasta el nivel objetivo
    for nivel in range(nivel_actual, MAX_NIVEL):
        xp_nivel = calcular_xp_necesaria(nivel)
        trabajos_necesarios = xp_nivel / xp_por_trabajo
        xp_acumulada += xp_nivel
        trabajos_acumulados = xp_acumulada / xp_por_trabajo
        
        trabajos_por_nivel[nivel + 1] = {
            "xp_necesaria": xp_nivel,
            "trabajos_para_este_nivel": int(trabajos_necesarios),
            "trabajos_acumulados": int(trabajos_acumulados)
        }
    
    return trabajos_por_nivel

def crear_tabla_progresion():
    """Crea una tabla de progresión para todos los trabajos
    
    Returns:
        str: Tabla formateada con la información de progresión
    """
    tabla = "```\n"
    tabla += "Nivel | Desbloqueo General\n"
    tabla += "------|-------------------------------------\n"
    tabla += "  2   | +10% Recompensa base\n"
    tabla += "  3   | -5% Energía requerida\n"
    tabla += "  4   | +15% Recompensa base\n"
    tabla += "  5   | ✨ Habilidad Especial Activa/Pasiva\n"
    tabla += "  6   | +20% Recompensa base\n"
    tabla += "  7   | -10% Energía requerida\n"
    tabla += "  8   | 🚀 Mecánica Avanzada (Gran Riesgo/Recompensa)\n"
    tabla += "  9   | 🏆 Título de Maestro desbloqueado\n"
    tabla += "  10  | +50% Recompensa, -15% Energía\n"
    tabla += "```\n"
    tabla += "💡 *Usa el botón 'Detalles' de cada trabajo en el menú principal para ver la habilidad exacta que se desbloquea.*"
    return tabla

def crear_embed_progresion_global():
    """Crea un embed con la información de progresión global para todos los niveles
    
    Returns:
        discord.Embed: Embed con la información de progresión
    """
    embed = discord.Embed(
        title="📊 Sistema de Niveles de Trabajo",
        description=(
            "Esta tabla muestra la progresión de niveles para todos los trabajos.\n"
            "La experiencia necesaria aumenta con cada nivel, pero las recompensas y bonificaciones también."
        ),
        color=discord.Color.gold()
    )
    
    # Añadir tabla de progresión
    embed.add_field(
        name="🔄 Tabla de Progresión",
        value=crear_tabla_progresion(),
        inline=False
    )
    
    # Añadir información sobre XP
    embed.add_field(
        name="✨ Experiencia (XP)",
        value=(
            f"🔸 **XP Base para Nivel 1:** {XP_BASE}\n"
            f"🔸 **Factor de aumento por nivel:** x{FACTOR_XP}\n"
            f"🔸 **Nivel Máximo:** {MAX_NIVEL}"
        ),
        inline=False
    )
    
    # Añadir información sobre cada trabajo
    trabajos_info = []
    for tipo, info in TIPOS_TRABAJO.items():
        trabajos_info.append(
            f"{info['emoji']} **{info['nombre']}**: {info['xp_por_trabajo']} XP por trabajo"
        )
    
    embed.add_field(
        name="💼 Trabajos Disponibles",
        value="\n".join(trabajos_info),
        inline=False
    )
    
    return embed

# La base de datos se configurará mediante la función setup_db() llamada explícitamente desde el cargador del módulo.

def get_job_header(user_id, tipo_trabajo):
    """Obtiene el encabezado estandarizado para iniciar un trabajo"""
    bonos = calcular_bonificaciones(user_id, tipo_trabajo)
    bono_energia = bonos["energia_reduccion"]
    bono_recompensa = bonos["recompensa_multiplicador"] - 1.0
    info = TIPOS_TRABAJO[tipo_trabajo]
    nivel_info = get_nivel_trabajo(user_id, tipo_trabajo)
    nivel = nivel_info["nivel"]
    bonificacion_actual = info['bonificaciones'].get(nivel, "Sin bonificaciones")
    energia_req = calcular_energia_requerida(info['energia_base'], user_id, tipo_trabajo)
    
    return (
        f"📈 **Tier:** {info.get('tier_economico', 'N/A')} | 🎯 **Riesgo:** {info.get('riesgo', 'N/A')}\n"
        f"💰 **Recompensa:** {info['recompensa_base']} base (+{int(bono_recompensa * 100)}% bono)\n"
        f"⚡ **Energía:** {energia_req} (-{int(bono_energia * 100)}%)\n"
        f"🌟 **Bonus (Nivel {nivel}):** {bonificacion_actual}\n\n"
    )
