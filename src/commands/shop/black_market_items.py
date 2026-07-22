# Catálogo completo de mejoras del Mercado Negro (Blackmarket)
# id: ID único de la mejora
# job: Nombre del oficio o 'general'/'casino'/'robar'
# tier: 1 a 5 (para oficios) o None
# rarity_weight: Peso para la rotación (50=Común, 30=Poco Común, 12=Raro, 6=Épico, 2=Mítico)

BLACK_MARKET = [
    # --- ARTEFACTOS ILEGALES Y ESPECIALES ---
    {
        "id": 100,
        "nombre": "Frasco de Silencio (Special Mute) 🤫",
        "precio": 10000,
        "descripcion": "Permite usar `/specialmute` para silenciar temporalmente las alertas públicas de robo.",
        "prestige_required": 0,
        "rarity_weight": 20,
        "job": "robar"
    },
    {
        "id": 101,
        "nombre": "Tarjeta Maestra 💳",
        "precio": 25000,
        "descripcion": "+15% probabilidad de éxito en `/robar` y -20% de multa si fallas (3 usos).",
        "prestige_required": 0,
        "rarity_weight": 15,
        "job": "robar"
    },
    {
        "id": 102,
        "nombre": "Ganzúa Blindada 🔑",
        "precio": 35000,
        "descripcion": "Si un robo falla, evita ser encarcelado o perder dinero el 100% de las veces (1 uso).",
        "prestige_required": 0,
        "rarity_weight": 10,
        "job": "robar"
    },
    {
        "id": 103,
        "nombre": "Soborno Policial 👮",
        "precio": 50000,
        "descripcion": "Limpia tu historial de delitos e ignora el escudo de 3 min de la víctima.",
        "prestige_required": 0,
        "rarity_weight": 8,
        "job": "robar"
    },
    {
        "id": 104,
        "nombre": "Dado Trucado 🎲",
        "precio": 40000,
        "descripcion": "Permite volver a tirar 1 vez en juegos de dados/ruleta si pierdes (máx 3/día).",
        "prestige_required": 0,
        "rarity_weight": 10,
        "job": "casino"
    },
    {
        "id": 105,
        "nombre": "Chip Hackeado 🎰",
        "precio": 60000,
        "descripcion": "Multiplica por x1.2 cualquier ganancia en tragaperras durante 15 minutos.",
        "prestige_required": 0,
        "rarity_weight": 8,
        "job": "casino"
    },
    {
        "id": 106,
        "nombre": "Corona del Prestigio 👑",
        "precio": 75000,
        "descripcion": "Ganas un 5% más de monedas en todos los trabajos y casinos combinados para siempre. [Prestigio II]",
        "prestige_required": 2,
        "rarity_weight": 5,
        "job": "general"
    },

    # --- 1. MINERO (5 Tiers) ---
    {"id": 201, "nombre": "Pico de Hierro Reforzado ⛏️ [Tier I]", "precio": 15000, "descripcion": "[Minero] -10% tiempo de cooldown al minar.", "job": "minero", "tier": 1, "rarity_weight": 50, "prestige_required": 0},
    {"id": 202, "nombre": "Casco con Linterna LED ⛏️ [Tier II]", "precio": 30000, "descripcion": "[Minero] +5% probabilidad de hallar gemas comunes.", "job": "minero", "tier": 2, "rarity_weight": 30, "prestige_required": 0},
    {"id": 203, "nombre": "Dinamita de Grava ⛏️ [Tier III]", "precio": 60000, "descripcion": "[Minero] Permite realizar 2 minados seguidos 1 vez al día.", "job": "minero", "tier": 3, "rarity_weight": 12, "prestige_required": 0},
    {"id": 204, "nombre": "Carrito de Mina Automatizado ⛏️ [Tier IV]", "precio": 120000, "descripcion": "[Minero] Protege el 15% de tus materiales minados ante robos.", "job": "minero", "tier": 4, "rarity_weight": 6, "prestige_required": 1},
    {"id": 205, "nombre": "Taladro de Diamante Ilegal ⛏️ [Tier V Mítico]", "precio": 250000, "descripcion": "[Minero] Permite extraer 'Fragmentos de Gema Mítica' para Raids.", "job": "minero", "tier": 5, "rarity_weight": 2, "prestige_required": 2},

    # --- 2. PESCADOR (5 Tiers) ---
    {"id": 211, "nombre": "Caña de Carbono 🎣 [Tier I]", "precio": 15000, "descripcion": "[Pescador] Zona segura de tensión +10% más amplia.", "job": "pescador", "tier": 1, "rarity_weight": 50, "prestige_required": 0},
    {"id": 212, "nombre": "Anzuelo Reluciente 🎣 [Tier II]", "precio": 30000, "descripcion": "[Pescador] +10% probabilidad de picada rápida.", "job": "pescador", "tier": 2, "rarity_weight": 30, "prestige_required": 0},
    {"id": 213, "nombre": "Red de Trazado Profundo 🎣 [Tier III]", "precio": 60000, "descripcion": "[Pescador] Captura 1 pez adicional en pescas exitosas.", "job": "pescador", "tier": 3, "rarity_weight": 12, "prestige_required": 0},
    {"id": 214, "nombre": "Sonar de Pesca Avanzado 🎣 [Tier IV]", "precio": 120000, "descripcion": "[Pescador] Muestra la rareza del pez antes de recoger el anzuelo.", "job": "pescador", "tier": 4, "rarity_weight": 6, "prestige_required": 1},
    {"id": 215, "nombre": "Arpón Electrificado 🎣 [Tier V Mítico]", "precio": 250000, "descripcion": "[Pescador] Ocasionalmente captura criaturas abisales míticas.", "job": "pescador", "tier": 5, "rarity_weight": 2, "prestige_required": 2},

    # --- 3. CHEF (5 Tiers) ---
    {"id": 221, "nombre": "Cuchillo de Damasco 🔪 [Tier I]", "precio": 14000, "descripcion": "[Chef] +15% de recompensa y XP en platos cocinados.", "job": "chef", "tier": 1, "rarity_weight": 50, "prestige_required": 0},
    {"id": 222, "nombre": "Especias Exóticas 🔪 [Tier II]", "precio": 28000, "descripcion": "[Chef] +10% de valor final al vender platillos.", "job": "chef", "tier": 2, "rarity_weight": 30, "prestige_required": 0},
    {"id": 223, "nombre": "Horno Convector Industrial 🔪 [Tier III]", "precio": 55000, "descripcion": "[Chef] Cocina 2 platillos simultáneos.", "job": "chef", "tier": 3, "rarity_weight": 12, "prestige_required": 0},
    {"id": 224, "nombre": "Recetario Ancestral 🔪 [Tier IV]", "precio": 110000, "descripcion": "[Chef] Desbloquea la categoría de banquetes de Prestigio.", "job": "chef", "tier": 4, "rarity_weight": 6, "prestige_required": 1},
    {"id": 225, "nombre": "Sartén de Titanio Mitológico 🔪 [Tier V Mítico]", "precio": 240000, "descripcion": "[Chef] Otorga platillos que restauran lealtad de mascotas al 100%.", "job": "chef", "tier": 5, "rarity_weight": 2, "prestige_required": 2},

    # --- 4. MECÁNICO (5 Tiers) ---
    {"id": 231, "nombre": "Herramientas de Precisión 🔧 [Tier I]", "precio": 18000, "descripcion": "[Mecánico] Penalización por diagnóstico erróneo -50%.", "job": "mecanico", "tier": 1, "rarity_weight": 50, "prestige_required": 0},
    {"id": 232, "nombre": "Escáner OBD-III 🔧 [Tier II]", "precio": 32000, "descripcion": "[Mecánico] Revela automáticamente el fallo en reparación.", "job": "mecanico", "tier": 2, "rarity_weight": 30, "prestige_required": 0},
    {"id": 233, "nombre": "Elevador Hidráulico 🔧 [Tier III]", "precio": 65000, "descripcion": "[Mecánico] +20% velocidad de reparación.", "job": "mecanico", "tier": 3, "rarity_weight": 12, "prestige_required": 0},
    {"id": 234, "nombre": "Banco de Pruebas ECU 🔧 [Tier IV]", "precio": 130000, "descripcion": "[Mecánico] Bonus de propina del cliente +25%.", "job": "mecanico", "tier": 4, "rarity_weight": 6, "prestige_required": 1},
    {"id": 235, "nombre": "Kit Tuning Ilegal 🔧 [Tier V Mítico]", "precio": 260000, "descripcion": "[Mecánico] Elimina 100% de errores de diagnóstico y otorga bonus legendario.", "job": "mecanico", "tier": 5, "rarity_weight": 2, "prestige_required": 2},

    # --- 5. ARTISTA (5 Tiers) ---
    {"id": 241, "nombre": "Caballete de Oro 🎨 [Tier I]", "precio": 16000, "descripcion": "[Artista] +10 creatividad base en todas las obras.", "job": "artista", "tier": 1, "rarity_weight": 50, "prestige_required": 0},
    {"id": 242, "nombre": "Pinceles de Pelo de Maza 🎨 [Tier II]", "precio": 30000, "descripcion": "[Artista] +15% de probabilidad de inspirarte.", "job": "artista", "tier": 2, "rarity_weight": 30, "prestige_required": 0},
    {"id": 243, "nombre": "Pigmentos Raros 🎨 [Tier III]", "precio": 60000, "descripcion": "[Artista] Eleva la valoración en subastas de arte.", "job": "artista", "tier": 3, "rarity_weight": 12, "prestige_required": 0},
    {"id": 244, "nombre": "Galería Privada 🎨 [Tier IV]", "precio": 120000, "descripcion": "[Artista] Genera ingresos pasivos continuos por tus cuadros.", "job": "artista", "tier": 4, "rarity_weight": 6, "prestige_required": 1},
    {"id": 245, "nombre": "Estudio Virtual Holográfico 🎨 [Tier V Mítico]", "precio": 250000, "descripcion": "[Artista] Obras maestras vendibles a precios astronómicos.", "job": "artista", "tier": 5, "rarity_weight": 2, "prestige_required": 2},

    # --- 6. HACKER (5 Tiers) ---
    {"id": 251, "nombre": "Procesador Cuántico 💻 [Tier I]", "precio": 20000, "descripcion": "[Hacker] Éxito de hackeo aumenta de 70% a 80%.", "job": "hacker", "tier": 1, "rarity_weight": 50, "prestige_required": 0},
    {"id": 252, "nombre": "Antena de Alta Ganancia 💻 [Tier II]", "precio": 35000, "descripcion": "[Hacker] Disminuye la probabilidad de ser rastreado.", "job": "hacker", "tier": 2, "rarity_weight": 30, "prestige_required": 0},
    {"id": 253, "nombre": "Bypass Firewall 💻 [Tier III]", "precio": 70000, "descripcion": "[Hacker] Otorga 1 intento extra al descifrar contraseñas.", "job": "hacker", "tier": 3, "rarity_weight": 12, "prestige_required": 0},
    {"id": 254, "nombre": "Botnet Criptográfica 💻 [Tier IV]", "precio": 140000, "descripcion": "[Hacker] Minado en segundo plano de criptos ficticias.", "job": "hacker", "tier": 4, "rarity_weight": 6, "prestige_required": 1},
    {"id": 255, "nombre": "Zero-Day Exploit 💻 [Tier V Mítico]", "precio": 280000, "descripcion": "[Hacker] Éxito de hackeo 95% garantizado con recompensas dobles.", "job": "hacker", "tier": 5, "rarity_weight": 2, "prestige_required": 2},

    # --- 7. PILOTO (5 Tiers) ---
    {"id": 261, "nombre": "Altímetro Digital ✈️ [Tier I]", "precio": 16000, "descripcion": "[Piloto] +10% estabilidad en vuelos de carga.", "job": "piloto", "tier": 1, "rarity_weight": 50, "prestige_required": 0},
    {"id": 262, "nombre": "Motor Sobrealimentado ✈️ [Tier II]", "precio": 32000, "descripcion": "[Piloto] -15% tiempo de trayecto en vuelo.", "job": "piloto", "tier": 2, "rarity_weight": 30, "prestige_required": 0},
    {"id": 263, "nombre": "GPS de Precisión ✈️ [Tier III]", "precio": 65000, "descripcion": "[Piloto] Evita turbulencias y pérdidas de carga.", "job": "piloto", "tier": 3, "rarity_weight": 12, "prestige_required": 0},
    {"id": 264, "nombre": "Radar Doppler ✈️ [Tier IV]", "precio": 130000, "descripcion": "[Piloto] Bonificación por aterrizajes perfectos +20%.", "job": "piloto", "tier": 4, "rarity_weight": 6, "prestige_required": 1},
    {"id": 265, "nombre": "Piloto Automático IA ✈️ [Tier V Mítico]", "precio": 260000, "descripcion": "[Piloto] Vuelos automatizados con cero riesgo de accidente.", "job": "piloto", "tier": 5, "rarity_weight": 2, "prestige_required": 2},

    # --- 8. CIENTÍFICO (5 Tiers) ---
    {"id": 271, "nombre": "Microscopio Electrónico 🔬 [Tier I]", "precio": 17000, "descripcion": "[Científico] +10% éxito en síntesis de laboratorio.", "job": "cientifico", "tier": 1, "rarity_weight": 50, "prestige_required": 0},
    {"id": 272, "nombre": "Reactivos Puros 🔬 [Tier II]", "precio": 33000, "descripcion": "[Científico] Reduce fallo de reactivos inestables.", "job": "cientifico", "tier": 2, "rarity_weight": 30, "prestige_required": 0},
    {"id": 273, "nombre": "Centrifugadora de Alta Velocidad 🔬 [Tier III]", "precio": 68000, "descripcion": "[Científico] Duplica la producción de muestras.", "job": "cientifico", "tier": 3, "rarity_weight": 12, "prestige_required": 0},
    {"id": 274, "nombre": "Espectrómetro de Masas 🔬 [Tier IV]", "precio": 135000, "descripcion": "[Científico] Bonus por descubrimientos raros +25%.", "job": "cientifico", "tier": 4, "rarity_weight": 6, "prestige_required": 1},
    {"id": 275, "nombre": "Acelerador de Partículas 🔬 [Tier V Mítico]", "precio": 270000, "descripcion": "[Científico] Permite crear elixires únicos de potencia mítica.", "job": "cientifico", "tier": 5, "rarity_weight": 2, "prestige_required": 2},

    # --- 9. MÉDICO (5 Tiers) ---
    {"id": 281, "nombre": "Estetoscopio de Titanio 🩺 [Tier I]", "precio": 15000, "descripcion": "[Médico] +10% precisión en diagnóstico de pacientes.", "job": "medico", "tier": 1, "rarity_weight": 50, "prestige_required": 0},
    {"id": 282, "nombre": "Kit de Sutura Láser 🩺 [Tier II]", "precio": 30000, "descripcion": "[Médico] Cura emergencias un +20% más rápido.", "job": "medico", "tier": 2, "rarity_weight": 30, "prestige_required": 0},
    {"id": 283, "nombre": "Desfibrilador Automático 🩺 [Tier III]", "precio": 62000, "descripcion": "[Médico] Salva operaciones críticas en estado de shock.", "job": "medico", "tier": 3, "rarity_weight": 12, "prestige_required": 0},
    {"id": 284, "nombre": "Cámara Hiperbárica 🩺 [Tier IV]", "precio": 125000, "descripcion": "[Médico] Otorga bonus de recuperación masiva a pacientes.", "job": "medico", "tier": 4, "rarity_weight": 6, "prestige_required": 1},
    {"id": 285, "nombre": "Suero Regenerativo Celular 🩺 [Tier V Mítico]", "precio": 250000, "descripcion": "[Médico] Éxito médico 100% garantizado con honorarios triples.", "job": "medico", "tier": 5, "rarity_weight": 2, "prestige_required": 2},
]
