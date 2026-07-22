# 📋 Informe de Continuidad — Bot Discord (Combate + Economía)

> Documento de referencia para retomar el trabajo con otra sesión de IA si esta se corta. Resume arquitectura, todo lo implementado y verificado, patrones establecidos, y el estado de la conversación en curso al momento de escribir esto.

## 🏗️ Arquitectura general

- **Dos economías separadas a propósito** (decisión confirmada, no se van a puentear):
  - **Combate** (duelos/raids/Aventura): moneda **Bronce/Plata/Oro** (100 Bronce = 1 Plata, 100 Plata = 1 Oro; se guarda como entero en Bronce, se muestra en denominación mixta vía `format_currency()`). Tabla `CombatWallet`.
  - **Economía general** (casino, trabajos, banco, bolsa, mascotas, tienda): moneda **Balance** (`Users.Balance`, ya era `BIGINT`).
- `src/commands/duels/raid.py` y `duelo.py` fueron **refactorizados en carpetas** (`src/commands/duels/raid/` con `boss.py`, `combatant.py`, `lobby_view.py`, `skill_views.py`, `loot_views.py`, `merchant_views.py` — el archivo `raid.py` original quedó con `RaidCombatView`/`RaidsCog` importando el resto). El refactor de `duelo.py` a carpeta **no se completó** (quedó pendiente tras el de `raid.py`).
- Servicios centralizados que **todo código nuevo debe usar**: `CasinoService` (place_bet/settle_win/settle_loss — algunos juegos todavía no lo usaban, se fueron encontrando casos sueltos como Crash), `EconomyService` (transfer_balance), `BancoService`/`bank_service.py` (préstamos + inversiones).

---

## ⚔️ Sistema de Combate — completado

- **15 subclases** (5 clases × 3 subclases), cada una con conversión de stats de equipo, skill Nv.10 y Nv.15 (ultimate), implementadas en duelo y raid.
- **Taxonomía de estados**: Veneno (stackea capas), Quemadura, Sangrado, Aturdimiento, Congelación (distinta de aturdimiento, alarga cooldowns), Silencio, Ceguera, Debilidad, Fragilidad, Vulnerabilidad (cap combinado +75%), Anti-cura, Frenesí, Escudo, HoT.
- **Softcap de equipo**: eficiencia 100% hasta el tope, 50% en el tramo 2 (100-200% del tope), 20% más allá.
- **Dificultad de raids**: Poder de Combate (nivel + equivalente de niveles por equipo/subclase), 3 dificultades (Normal/Difícil/Mítica, Mítica limitada a 2/día por jugador), bosses multi-fase + Fase de Furia (oleadas + dominación + stun grupal).
- **Add spawns por arquetipo** (Escudo/Curandero/Explosivo/Debilitador) + **Minibosses aleatorios** (Cofre Mimético, Espíritu Errante — Mercader Fantasma explícitamente pausado).
- **Ítems**: catálogo de ítems únicos (7, uno por boss) + **Sets de equipo** (7 sets, framework de bonus 2pc funcional, 7 efectos de bonus 4pc con flags listos pero **sin lógica de combate conectada a propósito** — quedaron como flags booleanos). 21 piezas adicionales de sets generadas por IA (28 ítems únicos totales).
- **20 pasivos de ítem** (10 originales + 10 estilo WoW con ICD/cooldown interno), **mini-afijos** (Épico/Legendario, 6 tipos), **subtipos de arma** (Daga/Espada/Lanza/Hacha, Bastón/Orbe/Tomo/Cetro) con modificadores mecánicos, **sistema de nombres en 4 capas** (Afijo/Subvariante/Variante/Mini afijo).
- **Economía de combate**: Gemas (6 tipos × 3 tiers = 18), Consumibles (4, incluye Frasco de Silencio), Ultimate de Equipo compartido en raid (barra que se llena con daño del grupo).
- **Bug fixes confirmados resueltos**: `boss_config`/`taunt_cooldown` (AttributeError por atributos no inicializados — patrón que se repitió 2 veces), habilidad especial ahora es privada/efímera por jugador (antes se veían las skills de todos en un dropdown compartido), dificultad que se reseteaba a Normal en timeout de ronda.
- **Diseñado pero NO implementado**: Robo en Banda de combate (N/A, esto es un sistema de robo de la economía general, no de combate — ver abajo), Tutorial de combate, sistema "Aventura" (PvE 1-10 rondas, 5 Lugares con roles de enemigo reutilizables, sin cooldown, recompensas modestas — diseño completo con números, **sin prompt de implementación todavía**), Poblado comunitario, Campañas.

---

## 💰 Economía General — completado

- **Casino**: 17 juegos. Auditoría de cobertura: **Provably Fair** (HMAC-SHA512) solo en Crash/Plinko/Casino War (el resto usa `random`/`secrets`). **Dificultad Dinámica** (ajuste oculto de probabilidades por historial del jugador) en 10 de 17 — tensión con Provably Fair ya divulgada en `/provably_fair` (decisión: mantener ambos, ser transparentes, no eliminar DD).
- **Bugs de casino corregidos**: Crash regalaba el "crash instantáneo" (mecanismo central del house edge) como ganancia garantizada — corregido. Slots usaba símbolos sin ponderar (RTP real 79% vs. tabla de pagos) — corregido a pesos calibrados (RTP ~93.8%, verificado por simulación exacta). Higher/Lower tenía multiplicador fijo (+30%/ronda) ignorando la probabilidad real de la carta, más un "redraw oculto" manipulado por Dificultad Dinámica — prompt de fix entregado (**confirmar si se aplicó**). Mines y Roulette ya estaban matemáticamente correctos (verificados contra fórmulas reales de la industria).
- **RNG**: Mines/Higher-Lower migrados a `secrets` (CSPRNG real) — Crash/Plinko ya usaban HMAC.
- **Bug crítico encontrado y corregido**: `GameHistory`/`GameResults` tenían columnas `INT` (tope 2.147M) en vez de `BIGINT` — causaba `NumericValueOutOfRange` en juegos con apuestas grandes. Al corregir, se encontraron 2 columnas más con el mismo problema (`GemCatalog.Price`, `ConsumableCatalog.Price`, del sistema de combate).
- **Bug crítico encontrado (17-jul)**: una cuenta llegó a **~85 billones de saldo** (muy por encima de cualquier techo diseñado). Diagnóstico: (a) 9 de 17 juegos sin cooldown, (b) **Crash tenía su propia función de pago (`process_crash_payout_atomic`) que bypasseaba `CasinoService` por completo** — sin impuesto de casino, sin cobertura del circuito de seguridad. Prompt de fix entregado (**confirmar si se aplicó**).
- **Sistema anti-inflación** (para atacar saldos descontrolados):
  - **Impuesto por Transacción** (`TRANSACTION_TAX` en `economy_config.py`): transferencia 2%, casino 3%, bolsa 1.5%, mercado 5% (reservado), subasta 8% (reservado) — dinero se **destruye**, no se redistribuye.
  - **Banco Central**: reservas alimentadas por impuestos; **préstamos** (0.5%/día interés, 7 días plazo, mora retiene 10% de sueldos — bug encontrado y corregido: la mora no se limpiaba sola al pagarse vía retención); **Inversiones** (7 días, tabla de probabilidad con EV ligeramente positivo ~+1.5%, bloqueado si `EnMora`).
  - **Cuota de Protección** (reemplazó el viejo sistema de protección por horas): 500k+ de saldo, cobro diario progresivo (1-5%), **escudo contra `/robar` de 3 min base / 30 min si pagaste la cuota** (diseño explícito del usuario).
  - **Prestigio**: idle-style, 7 niveles exponenciales (umbral ×15 desde 100k hasta ~1,1 billones), reset de saldo a 10k semilla al prestigiar, contenido de niveles I/II/III mayormente implementado (ver detalle abajo). **Prestigio forzado** en umbral de emergencia (~11,4 billones) diseñado, prompt entregado (**confirmar si se aplicó**).
  - **Bolsa Simulada**: 6 activos (3 acciones estables + 3 criptos volátiles), caminata aleatoria geométrica calibrada matemáticamente (sigma_tick por activo según tiempo-a-cambio-notorio: 1h volátil / 24h estable), dividendos (solo acciones), tick cada 5s en memoria + persistencia cada 2 min. **Implementado y verificado** — motor de precios revisado, fórmula correcta.
- **Sistema de robo — reconstruido**: bug crítico encontrado (la multa por fallar se calculaba sobre el saldo de la VÍCTIMA, no del ladrón — podía vaciar al 100% a alguien que atacara a un rico) — corregido para que la multa sea % del saldo propio. Tope de XP ganada al 10% de lo necesario para el nivel actual (evita saltos de 20+ niveles en un robo). Mecánicas nuevas diseñadas (Especialización de ladrón en nivel 8, Robo Silencioso, Golpe Perfecto, Inmunidad de Venganza, Ver objetivo, Golpe de Gracia, título visible) — prompt entregado. **Robo en Banda** (2 ladrones coordinados, todo efímero/privado) y **Robo al Banco Central** (máx. 1M, mecánicas propias) diseñados, prompt entregado — **confirmar si se aplicaron, ninguno de estos 2 últimos ha sido verificado todavía**.
- **Seguridad adicional diseñada, prompts entregados sin confirmar implementación**:
  - Circuito de seguridad universal: ganar 25% del saldo de referencia → bloqueo de casino de 25 min (aplica a todos los juegos vía `CasinoService`).
  - Circuit breaker por juego: si un juego paga >25% de la economía TOTAL del servidor en 1 día, se autodesactiva 2 horas.
  - Bloqueo de fila (`FOR UPDATE`) en todas las rutas de saldo que lean-antes-de-escribir (auditoría, hoy solo 5 lugares en todo `db.py` lo tienen).

### Contenido de Prestigio (niveles I/II/III) — implementado con confirmaciones
- **Nivel I** (100k): insignia visual, -5% cooldown trabajos, +1 ticket lotería, `/flex`, -5% tienda normal, emoji de reacción **descartado** (no viable multi-servidor).
- **Nivel II** (1.5M): Corona del Prestigio (Blackmarket, +5% ingresos), 2do préstamo simultáneo (`LoanSlot` como parte de PK compuesta), -20% Cuota de Protección, ítems de oficio "[Prestigio]" doble efecto (6 de 9 oficios cubiertos — **verificar si faltan 3**), límite de préstamo base más alto, consumible de protección total 24h.
- **Nivel III** (22.5M): estadísticas avanzadas, -15% interés banco, escudo 45 min, **bono mensual 100k** (prompt entregado, confirmar). Multiplicador de apuesta máxima **pausado** (no hay tope de apuesta general todavía). Torneo de Casino / mini-torneos **explícitamente diferidos** para el final.

---

## 🐛 Patrón recurrente detectado (importante para cualquier IA que continúe)

A lo largo de todo el proyecto, la IA que implementa **tiende a resolver ambigüedades marcadas como "detente y pregunta" en vez de pausar** — en la mayoría de los casos la resolución fue razonable, pero no siempre se confirmó con el usuario antes. Recomendación: si algo es una decisión de diseño real (no solo técnica), usar instrucciones más contundentes tipo "STOP, no implementes X sin confirmar" y revisar explícitamente ese punto al recibir el resultado.

También se ha encontrado repetidamente el patrón de **funciones de pago/lógica duplicadas que bypasean el servicio centralizado** (Crash con Balance, pets_logic.py con funciones muertas duplicando pets.py) — vale la pena, en algún momento, un barrido sistemático buscando otros casos similares no descubiertos todavía.

---

## 🎯 Conversación en curso al momento de escribir esto — Mascotas/Tienda/Blackmarket (rediseño grande)

El usuario pidió una lista de mejoras antes de implementar, luego agregó ideas concretas nuevas:

### Mascotas
- **3 slots de mascota activos simultáneos**: uno para Casino, uno para Robar, uno para Raids (combate) — pendiente definir qué efecto concreto da el slot de Raids (no debe cruzar monedas, ya que las economías están separadas a propósito — probablemente un bonus cosmético/menor dentro de combate, no conversión de dinero).
- Expandir catálogo con muchas mascotas nuevas, cada una con característica propia (no solo tiers del mismo efecto).
- 3 formas de obtención: actividad con el bot (ya existe, `check_pet_encounter`), aleatoria, y **compra en tienda** (nueva).
- **Fusión de 5 iguales → 1 aleatoria de rareza superior**: **YA EXISTE**, `/pet_fusionar`, funciona exactamente como se pidió (Normal→Rara→Épica→Legendaria→Mítica). No requiere trabajo nuevo.
- **Venta de mascotas**: no existe todavía, hay que diseñarla (a quién se vende, por cuánto — probablemente un precio fijo por rareza, o vía el nuevo mercado de usuarios).

### Tienda de usuarios (mercado/subastas — sistema nuevo grande)
- Funciona tanto para ítems de combate (raid) como de economía general (cada uno en su propia moneda, sin cruzarse).
- 2 modos de venta: **compra instantánea** (precio fijo puesto por el dueño) o **subasta** (precio inicial + pujas).
- Duración de listado: 4, 8, o 12 horas (elegible por el vendedor).
- Cobra comisión — coincide con las tasas ya reservadas en `TRANSACTION_TAX["mercado"]` (5%) y `["subasta"]` (8%), nunca implementadas hasta ahora.

### Tienda + Blackmarket → Stock rotativo
- Reemplaza los catálogos estáticos actuales por **stock aleatorio con cantidad limitada por ítem**, rotando cada 3 horas.
- Si se agota un ítem, no vuelve automáticamente en la siguiente rotación — la probabilidad de reaparecer depende de la rareza/cantidad configurada del ítem.

### Lootboxes de mascotas con animación estilo CS:GO
- Cajas comprables con contenido aleatorio de mascotas, con una animación de apertura tipo "case opening" (reel deslizante) — en Discord esto se simula editando el mensaje varias veces en secuencia para dar sensación de movimiento antes de revelar el resultado final.

### Confirmado: NO habrá puente entre las 2 economías (decisión final del usuario, ya no está en discusión).

## 📌 Próximo paso pendiente (justo donde se cortó la conversación)
Falta: (1) definir el efecto concreto del slot de mascota "Raids", (2) diseñar el precio/mecánica de venta de mascotas, (3) diseñar números concretos del mercado de usuarios (comisión exacta, límites), (4) diseñar la probabilidad de restock del stock rotativo, (5) diseñar el catálogo de lootboxes. Ninguno de los 5 prompts de esta sección se ha escrito todavía.