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
        'dificultad': 3,  # 1-5 donde 5 es más difícil
        'xp_por_trabajo': 15,  # XP base por trabajo completado
        'bonificaciones': {
            # nivel: {bonificación}
            1: 'Acceso a tareas básicas',
            2: '+10% recompensa base',
            3: '-5% energía requerida',
            4: '+15% recompensa base',
            5: 'Desbloquea tareas avanzadas',
            6: '+20% recompensa base',
            7: '-10% energía requerida',
            8: '+25% recompensa base',
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
        'dificultad': 2,
        'xp_por_trabajo': 12,
        'bonificaciones': {
            1: 'Acceso a recetas básicas',
            2: '+10% recompensa base',
            3: '-5% energía requerida',
            4: '+15% recompensa base',
            5: 'Desbloquea recetas avanzadas',
            6: '+20% recompensa base',
            7: '-10% energía requerida',
            8: '+25% recompensa base',
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
        'dificultad': 1,
        'xp_por_trabajo': 10,
        'bonificaciones': {
            1: 'Acceso a obras básicas',
            2: '+10% recompensa base',
            3: '-5% energía requerida',
            4: '+15% recompensa base',
            5: 'Desbloquea obras avanzadas',
            6: '+20% recompensa base',
            7: '-10% energía requerida',
            8: '+25% recompensa base',
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
        'dificultad': 4,
        'xp_por_trabajo': 20,
        'bonificaciones': {
            1: 'Acceso a reparaciones básicas',
            2: '+10% recompensa base',
            3: '-5% energía requerida',
            4: '+15% recompensa base',
            5: 'Desbloquea reparaciones avanzadas',
            6: '+20% recompensa base',
            7: '-10% energía requerida',
            8: '+25% recompensa base',
            9: 'Desbloquea reparaciones maestras',
            10: '+50% recompensa, -15% energía'
        }
    }
}

def setup_db():
    """Verifica la base de datos para el sistema de niveles de trabajo"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Verificar que existe la tabla joblevels
    cursor.execute("""
    IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'joblevels')
    BEGIN
        -- Crear tabla joblevels si no existe (aunque debería existir)
        CREATE TABLE joblevels (
            ID INT IDENTITY(1,1) PRIMARY KEY,
            UserId BIGINT,
            JobType VARCHAR(20),
            CompletedJobs INT DEFAULT 0,
            CreatedAt DATETIME DEFAULT GETDATE(),
            UpdatedAt DATETIME DEFAULT GETDATE()
        )
    END
    """)
    
    # Verificar si necesitamos añadir columnas para el sistema de niveles mejorado
    cursor.execute("""
    IF NOT EXISTS (SELECT * FROM sys.columns WHERE name = 'Level' AND object_id = OBJECT_ID('joblevels'))
    BEGIN
        ALTER TABLE joblevels ADD Level INT DEFAULT 0;
    END
    """)
    
    cursor.execute("""
    IF NOT EXISTS (SELECT * FROM sys.columns WHERE name = 'Experience' AND object_id = OBJECT_ID('joblevels'))
    BEGIN
        ALTER TABLE joblevels ADD Experience INT DEFAULT 0;
    END
    """)
    
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
    
    # Asegurarse de que existe la entrada para el usuario y tipo de trabajo
    cursor.execute("""
    IF NOT EXISTS (SELECT 1 FROM joblevels WHERE UserId = ? AND JobType = ?)
    BEGIN
        INSERT INTO joblevels (UserId, JobType, CompletedJobs, Level, Experience)
        VALUES (?, ?, 0, 0, 0)
    END
    """, user_id, tipo_trabajo, user_id, tipo_trabajo)
    
    # Consultar datos
    cursor.execute("""
    SELECT ISNULL(Level, 0) AS Level, 
           ISNULL(Experience, 0) AS Experience, 
           CompletedJobs
    FROM joblevels
    WHERE UserId = ? AND JobType = ?
    """, user_id, tipo_trabajo)
    
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
    SET Level = ?, 
        Experience = ?, 
        CompletedJobs = CompletedJobs + 1, 
        UpdatedAt = GETDATE()
    WHERE UserId = ? AND JobType = ?
    """, nivel_nuevo, xp_nueva, user_id, tipo_trabajo)
    
    conn.commit()
    conn.close()
    
    return {
        "nivel_anterior": nivel_actual,
        "nivel_nuevo": nivel_nuevo,
        "subio_nivel": subio_nivel,
        "xp_actual": xp_nueva,
        "xp_para_siguiente": calcular_xp_necesaria(nivel_nuevo) if nivel_nuevo < MAX_NIVEL else 0
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
           ISNULL(Level, 0) AS Level, 
           ISNULL(Experience, 0) AS Experience, 
           CompletedJobs
    FROM joblevels
    WHERE UserId = ?
    """, user_id)
    
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
    tabla += "Nivel | XP Necesaria | Bonificaciones\n"
    tabla += "------|-------------|-------------\n"
    
    for nivel in range(1, MAX_NIVEL + 1):
        # XP necesaria para este nivel
        if nivel == 1:
            xp_necesaria = XP_BASE
        else:
            xp_necesaria = calcular_xp_necesaria(nivel - 1)
            
        # Usar bonificaciones del primer trabajo como referencia (son iguales)
        bonificaciones = []
        for tipo, info in TIPOS_TRABAJO.items():
            if nivel in info['bonificaciones']:
                bonificacion = info['bonificaciones'][nivel]
                if bonificacion not in bonificaciones:
                    bonificaciones.append(bonificacion)
                break
        
        bonificacion_txt = ', '.join(bonificaciones)
        tabla += f"{nivel:<5} | {xp_necesaria:<11} | {bonificacion_txt}\n"
    
    tabla += "```"
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

# Asegurar que la base de datos esté configurada al importar el módulo
setup_db()
