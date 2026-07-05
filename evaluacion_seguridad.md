# ⚔️ Abuso de Interacciones, Spam de Cooldowns y Exploits Cruzados

Este documento contiene una auditoría de seguridad exhaustiva para el sistema económico y de juegos del bot de Discord. El análisis parte de una premisa fundamental de seguridad en desarrollo de bots:

> Los usuarios siempre intentarán romper el flujo de una interacción, y spamearán comandos en el milisegundo exacto en que un cooldown deba terminar. Además, el motor de un exploit rara vez se encuentra en un solo comando de forma aislada, sino en el punto de fricción donde dos mecánicas independientes comparten el mismo recurso limitante (saldo, energía, inventario, un botón).

---

## 🚨 Resumen de Gravedad de Vulnerabilidades

| # | Vulnerabilidad | Eje | Gravedad | Estado |
| :--- | :--- | :--- | :--- | :--- |
| **N1** | [Cashout de Mines sin verificación de game_over](#n1-cashout-de-mines-sin-verificacion-de-game_over-dinero-infinito) | Flujo | **CRÍTICA 🔴** | Vulnerable |
| **N2** | [Duplicación de jugador en la lobby de Ruleta Rusa](#n2-duplicacion-de-jugador-en-la-lobby-de-ruleta-rusa) | Flujo | **ALTA 🔴** | Vulnerable |
| **N3** | [Ausencia estructural de cooldowns nativos de Discord](#n3-ausencia-estructural-de-cooldowns-nativos-de-discord) | Spam | **CRÍTICA 🔴** | Vulnerable |
| **N4** | [Ventana de carrera en /daily (Reclamo doble + racha inflada)](#n4-ventana-de-carrera-en-daily-reclamo-doble--racha-inflada) | Spam | **ALTA 🔴** | Vulnerable |
| **N5** | [Pool de energía compartido sin bloqueo en /trabajo](#n5-pool-de-energia-compartido-sin-bloqueo-entre-los-11-minijuegos-de-trabajo) | Cruzado | **CRÍTICA 🔴** | Vulnerable |
| **N6** | [Combinación N1 + N5: Granja de trabajo y cashout infinito](#n6-combinacion-n1--n5-granja-de-trabajo-y-cashout-infinita) | Cruzado | **CRÍTICA 🔴** | Vulnerable |
| **N7** | [Ticket de Crash + ausencia de cooldown (N3)](#n7-ticket-de-crash--ausencia-de-cooldown-n3) | Cruzado | **ALTA 🔴** | Vulnerable |
| **1.1**| [Duplicación de saldo al rechazar Duelo en Coinflip](#11-duplicacion-de-monedas-al-rechazar-duelo-en-coinflip) | Flujo | **CRÍTICA 🔴** | Vulnerable |
| **1.2**| [Doble Aceptación de Duelo en Coinflip](#12-doble-aceptacion-de-duelo-en-coinflip) | Flujo | **ALTA 🔴** | Vulnerable |
| **1.3**| [Payout Múltiple en Blackjack al Plantarse](#13-payout-multiple-en-blackjack-al-plantarse) | Flujo | **ALTA 🔴** | Vulnerable |
| **2.1**| [Evasión del Cooldown de Robos](#21-evasion-del-cooldown-de-robos) | Spam | **MEDIA-ALTA 🟡** | Vulnerable |
| **2.2**| [Bypaseo de Límite Diario de Loto](#22-bypaseo-de-limite-diario-de-boletos-de-loteria) | Spam | **MEDIA 🟡** | Vulnerable |
| **3.1**| [La Paradoja del Ticket Crash (EV+ Infinito)](#31-la-paradoja-del-ticket-crash-explotacion-matematica-de-ev-positivo) | Cruzado | **ALTA 🔴** | Vulnerable |
| **3.2**| [Compra Gratuita / Duplicación de Ítems en Tienda](#32-compra-gratuita--duplicacion-de-items-en-la-tienda) | Cruzado | **MEDIA-ALTA 🟡** | Vulnerable |
| **3.3**| [Duplicación de Amuleto de Protección (Minería/Pesca)](#33-duplicacion-de-amuleto-de-proteccion-en-mineria-y-pesca) | Cruzado | **MEDIA 🟡** | Vulnerable |
| **3.4**| [Doble Uso de Tickets Consumibles en Slots](#34-doble-uso-de-tickets-consumibles-en-slots) | Cruzado | **MEDIA 🟡** | Vulnerable |
| **3.5**| [Evasión del Escudo Anti-Mute por Ataques Paralelos](#35-evasion-del-escudo-anti-mute-por-ataques-paralelos) | Cruzado | **MEDIA 🟡** | Vulnerable |

---

## 1️⃣ Eje: Interacciones que rompen el flujo

Este eje comprende las vulnerabilidades donde un botón, callback o modal interactivo ejecuta acciones económicas (como sumar/descontar dinero) sin comprobar adecuadamente si el flujo de interacción ya se ha completado o si la lógica ya fue ejecutada por otra corrutina paralela.

### N1. Cashout de Mines sin verificación de game_over (dinero infinito)
* **Archivo:** [mines.py](file:///c:/Users/Felipe/Desktop/Proyectos/Bot%20Discord/src/commands/casino/mines.py#L68-L83) — Clase `CashoutButton`
* **Gravedad:** **CRÍTICA 🔴**
* **Descripción:**
  El botón de retiro de ganancias de Mines no comprueba el estado del juego (`self.game_over`) al recibir la interacción. Aunque la función llamada `process_win` pone `self.game_over = True` como su primera línea de ejecución, esta corrutina realiza una llamada asíncrona a la base de datos para transferir el saldo:
  
  ```python
  # Dentro de MinesView
  async def process_win(self, interaction: discord.Interaction):
      self.game_over = True # <-- Se ejecuta en Python
      ...
      await asyncio.to_thread(add_balance, self.user_id, winnings) # <-- Punto de suspensión
  ```
  Dado que `process_win` se suspende en el `await`, si el usuario presiona el botón múltiples veces antes de que se complete la primera transacción, el botón llamará a `process_win` concurrentemente múltiples veces.
  
#### 🎮 Demostración del Exploit:
1. El usuario apuesta `50,000` monedas en `/mines` y revela al menos una gema.
2. Presiona "Retirarse" (Cashout) y, utilizando un autoclicker o haciendo clics rápidos repetidos, manda 10 solicitudes en 200 milisegundos.
3. El bot recibe y procesa todas las solicitudes. Como el botón no valida `view.game_over`, cada interacción pasa la validación y llama a `process_win`.
4. La base de datos recibe 10 comandos `add_balance` consecutivos para el mismo juego, acreditando las ganancias 10 veces consecutivas.
5. **Resultado:** El usuario multiplica sus ganancias por `N` de forma garantizada.

---

### N2. Duplicación de jugador en la lobby de Ruleta Rusa
* **Archivo:** [russian_roulette.py](file:///c:/Users/Felipe/Desktop/Proyectos/Bot%20Discord/src/commands/casino/russian_roulette.py#L21-L40) — `RRLobbyView.btn_join`
* **Gravedad:** **ALTA 🔴**
* **Descripción:**
  El botón "Unirse al Juego" valida si el usuario ya está registrado en la lobby con `if interaction.user in self.players:`. Sin embargo, la deducción del saldo de entrada y la inicialización del usuario se hacen asíncronamente con un `await` *antes* de agregar el usuario a la lista:
  
  ```python
  async def btn_join(self, interaction: discord.Interaction, button: discord.ui.Button):
      if interaction.user in self.players: # <-- Comprobación inicial
          return
      ...
      success, balance = await asyncio.to_thread(deduct_balance, user_id, self.bet) # <-- await
      ...
      self.players.append(interaction.user) # <-- Registro en la lista
  ```

#### 🎮 Demostración del Exploit:
1. Un usuario hace doble clic muy rápido en "Unirse al Juego" en la lobby de la Ruleta Rusa.
2. Ambas ejecuciones pasan la validación de `interaction.user in self.players` porque el usuario no ha sido agregado todavía en ninguna.
3. Se descuenta la entrada al usuario dos veces, pero se registra dos veces en la lista `self.players`.
4. El pozo total del juego se calcula como `self.bet * len(self.players)`, de forma que el pozo se infla contando al mismo usuario por dos. El usuario tiene dos vidas en el cilindro, rompiendo por completo las probabilidades justas del minijuego.

---

### 1.1. Duplicación de monedas al rechazar Duelo en Coinflip
* **Archivo:** [coinflip.py](file:///c:/Users/Felipe/Desktop/Proyectos/Bot%20Discord/src/commands/casino/coinflip.py#L113-L132) — Clase `CoinflipDuelView.decline_duel`
* **Gravedad:** **CRÍTICA 🔴**
* **Descripción:**
  Cuando el retador inicia un duelo, su saldo se debita de inmediato. Si la víctima rechaza el duelo presionando **❌ Rechazar Duelo**, el bot devuelve el saldo. El callback `decline_duel` no verifica la bandera `self.game_over` al inicio de su ejecución, sino que la establece a `True` y luego se suspende esperando la base de datos:
  
  ```python
  self.game_over = True
  await asyncio.to_thread(add_balance, self.challenger.id, self.apuesta)
  ```
  Si se envían solicitudes de rechazo simultáneas, la base de datos acreditará el reembolso tantas veces como clics se hayan realizado.

---

### 1.2. Doble Aceptación de Duelo en Coinflip
* **Archivo:** [coinflip.py](file:///c:/Users/Felipe/Desktop/Proyectos/Bot%20Discord/src/commands/casino/coinflip.py#L21-L36) — Clase `CoinflipDuelView.accept_duel`
* **Gravedad:** **ALTA 🔴**
* **Descripción:**
  Al hacer clic en **✅ Aceptar Duelo**, se comprueba el saldo de la víctima y se descuenta su dinero con `await asyncio.to_thread(deduct_balance, ...)`. Las banderas de bloqueo `self.game_started` y `self.game_over` se definen como `True` **después** del `await`. Dos clics paralelos causarán un doble descuento del retado, y el posterior pago doble de la moneda a quien resulte ganador, generando monedas del aire.

---

### 1.3. Payout Múltiple en Blackjack al Plantarse
* **Archivo:** [blackjack.py](file:///c:/Users/Felipe/Desktop/Proyectos/Bot%20Discord/src/commands/casino/blackjack.py#L113-L126) — Clase `BlackjackView.stand_button`
* **Gravedad:** **ALTA 🔴**
* **Descripción:**
  Al presionar **🛑 Plantarse**, se ejecuta un `await interaction.response.defer()` antes de marcar `self.game_over = True`. Esto permite que otra solicitud concurrente de plantarse pase el filtro de validación y ejecute `_finish_game` múltiples veces en paralelo, pagando la apuesta al jugador varias veces si este resulta ganador.

---

## 2️⃣ Eje: Spam en el borde exacto del cooldown

Este eje abarca cómo la falta de restricciones a nivel de Discord o la verificación no atómica de marcas de tiempo en base de datos permiten a los usuarios automatizar comandos para ejecutarlos en ráfagas de milisegundos y eludir cooldowns de negocio.

### N3. Ausencia estructural de cooldowns nativos de Discord
* **Gravedad:** **CRÍTICA (estructural) 🔴**
* **Descripción:**
  Una búsqueda en el proyecto revela que **ningún comando** implementa el decorador `@app_commands.checks.cooldown(...)` de Discord.py.
  Esto delega la prevención del spam exclusivamente a comprobaciones manuales en base de datos. Esto expone al bot a ráfagas ilimitadas de solicitudes que pueden saturar el pool de conexiones de PostgreSQL.

#### 🎮 Ventana de carrera en el borde de cooldowns manuales:
Para los comandos que implementan cooldowns en BD (como `/robar`, `/daily`, `/specialmute`), la lógica sigue un flujo no atómico:
$$\text{Lectura de Timestamp} \rightarrow \text{Comparación en Python} \rightarrow \text{Escritura del nuevo Timestamp}$$
Si un script spamea solicitudes en ráfagas de milisegundos justo en el instante en que el cooldown expira, todas las solicitudes leerán el timestamp antiguo y pasarán el check antes de que la primera transacción escriba el nuevo timestamp. El usuario consigue ejecutar el comando 2 a 5 veces en la misma ventana antes de bloquearse nuevamente.

---

### N4. Ventana de carrera en /daily (Reclamo doble + racha inflada)
* **Archivo:** [db.py](file:///c:/Users/Felipe/Desktop/Proyectos/Bot%20Discord/src/db.py#L640-L694) — Función `claim_daily`
* **Gravedad:** **ALTA 🔴**
* **Descripción:**
  La función `claim_daily` no aplica un bloqueo `FOR UPDATE` a la fila del usuario en la tabla `Users` al leer la columna `LastLogin`.
  
  ```python
  cursor.execute("SELECT LastLogin, Streak, Balance FROM Users WHERE UserID = %s", (user_id,))
  # ... validaciones de fecha en Python ...
  # ... posterior UPDATE de LastLogin y Balance ...
  ```

#### 🎮 Demostración del Exploit:
1. Justo al cambiar el día (o en el primer login de un usuario), se envían dos comandos `/daily` de forma paralela.
2. Ambas transacciones leen `LastLogin` como el día de ayer. Pasan la verificación de "ya reclamado".
3. Ambas otorgan el pago de monedas al balance y actualizan la racha (`Streak`).
4. **Resultado:** El usuario recibe el doble de dinero correspondiente al reclamo diario y manipula su racha de forma inconsistente.

---

### 2.1. Evasión del Cooldown de Robos
* **Archivo:** [robar.py](file:///c:/Users/Felipe/Desktop/Proyectos/Bot%20Discord/src/commands/actions/robar.py#L51-L62) — Función `_ejecutar_robo_db`
* **Gravedad:** **MEDIA-ALTA 🟡**
* **Descripción:**
  Aunque `_ejecutar_robo_db` bloquea las filas de la tabla `Users` usando `SELECT FOR UPDATE` para evitar inconsistencias en el dinero, **no bloquea** el registro de estadísticas de la tabla `RoboStats`.
  Dado que la base de datos se ejecuta en nivel de aislamiento `READ COMMITTED`, si se envían dos solicitudes de robo simultáneas, ambas leerán el valor antiguo de `LastRoboTime` de la tabla `RoboStats` antes de que se complete la primera transacción, ejecutando los dos robos seguidos de forma inmediata y saltándose el cooldown del rol de ladrón.

---

### 2.2. Bypaseo de Límite Diario de Loto
* **Archivo:** [lottery_service.py](file:///c:/Users/Felipe/Desktop/Proyectos/Bot%20Discord/src/services/lottery_service.py#L57-L59) — `LotteryService.purchase_ticket`
* **Gravedad:** **MEDIA 🟡**
* **Descripción:**
  El límite diario de 5 boletos de lotería se lee de forma independiente de la base de datos antes de realizar la inserción del nuevo boleto:
  ```python
  current_count = await asyncio.to_thread(get_user_ticket_count, user_id)
  if current_count >= 5:
      return False, "Límite alcanzado", 0
  ```
  Un spam de compras simultáneas permite a múltiples tareas asíncronas ver un recuento de 4 boletos y proceder con la compra, permitiendo comprar más boletos de los autorizados por día.

---

## 3️⃣ Eje: Interacciones cruzadas y exploits combinados

Este eje cubre las fallas de lógica más complejas, donde múltiples comandos o mecánicas independientes comparten el mismo recurso e interactúan entre sí de tal forma que se genera una vulnerabilidad sistémica de la economía que no existiría si los comandos se jugaran solos.

### N5. Pool de energía compartido sin bloqueo entre los 11 minijuegos de /trabajo
* **Archivo:** [energia.py](file:///c:/Users/Felipe/Desktop/Proyectos/Bot%20Discord/src/commands/economy/energia.py#L20-L27) — Función `consumir_energia`
* **Gravedad:** **CRÍTICA 🔴**
* **Descripción:**
  La función `consumir_energia` lee y escribe la energía de forma no atómica a través de dos consultas independientes (`get_energia` y `set_energia`):
  
  ```python
  def consumir_energia(user_id: int, cantidad: int) -> bool:
      energia_actual = get_energia(user_id) # <-- Consulta independiente (SELECT)
      if energia_actual >= cantidad:
          set_energia(user_id, energia_actual - cantidad) # <-- Escritura independiente (UPDATE)
          return True
      return False
  ```
  La energía es un recurso compartido por los 11 minijuegos interactivos de `/trabajo`. Cada minijuego descuenta la energía de manera aislada.

#### 🎮 Demostración del Exploit:
1. El usuario tiene `30` de energía (suficiente para iniciar solo un trabajo como Mecánico, que cuesta 30).
2. Abre 5 hilos en Discord y ejecuta paralelamente 5 trabajos: Mecánico (costo 30), Hacker (costo 25), Chef (costo 20), Artista (costo 15) y Minero (costo 15).
3. Todos los minijuegos consultan `get_energia` y leen el valor de 30 antes de que se ejecute la resta de alguno de ellos.
4. Todos pasan la comprobación `energia_actual >= cantidad` y se inician con éxito.
5. El usuario gana el dinero y la XP de los 5 trabajos, consumiendo una fracción mínima de energía y pisando el saldo final de la energía con el último cálculo que se guarde.

---

### N6. Combinación N1 + N5: Granja de trabajo y cashout infinita
* **Gravedad:** **CRÍTICA 🔴 (Exploit Compuesto)**
* **Descripción:**
  La combinación de la vulnerabilidad de energía compartida (N5) y el cashout ilimitado de Mines (N1) crea una anomalía de flujo económica:
  1. El usuario abre `/mines` en un canal y revela un diamante, dejando el botón de retiro listo.
  2. En paralelo, explota la energía compartida (N5) abriendo varios canales de `/trabajo` y recolectando ganancias sin gastar su energía real.
  3. Finalmente, presiona el botón de cashout de Mines con un autoclicker (N1) para multiplicar la ganancia del casino.
  El usuario multiplica exponencialmente su capital acumulando ambos exploits de forma paralela en la misma sesión.

---

### N7. Ticket de Crash + ausencia de cooldown (N3)
* **Gravedad:** **ALTA 🔴 (Exploit Compuesto)**
* **Descripción:**
  Como se analizó en la anomalía del Ticket de Crash (EV+), la protección contra explosiones antes de `1.50x` permite ganar 25,300 monedas promedio por ronda de forma garantizada apostando 100,000 monedas y retirándose a `x1.40`.
  Al no tener cooldowns nativos de Discord en `/crash` (N3), un script de automatización puede ejecutar este juego de forma inmediata sin tiempo de espera entre partidas, generando millones de monedas de forma exponencial y pasiva.

---

### 3.1. La Paradoja del Ticket Crash (Explotación Matemática de EV Positivo)
* **Archivo:** [crash.py](file:///c:/Users/Felipe/Desktop/Proyectos/Bot%20Discord/src/commands/casino/crash.py#L324-L349) — `CrashView.run_crash`
* **Gravedad:** **ALTA 🔴**
* **Descripción:**
  El `Ticket de Suerte Crash` (ID 6) cuesta `2,000` monedas en la tienda y reembolsa la apuesta si explota antes de `x1.50`. Si el juego supera `x1.50` y el usuario se retira en `x1.40` (obteniendo un retorno de ganancias del 40% neto), el ticket no se consume. Esto genera una ventaja matemática con un Valor Esperado (EV) positivo de **+25,300 monedas por ronda** para apuestas de 100k, arruinando el balance económico de pérdidas del casino del bot.

---

### 3.2. Compra Gratuita / Duplicación de Ítems en la Tienda
* **Archivo:** [tienda.py](file:///c:/Users/Felipe/Desktop/Proyectos/Bot%20Discord/src/commands/shop/tienda.py#L26-L43) — Función `_comprar_articulo_db`
* **Gravedad:** **MEDIA-ALTA 🟡**
* **Descripción:**
  La compra de artículos deduce el balance y añade el ítem en transacciones separadas no atómicas. El saldo se lee con `get_balance` y se descuenta con `set_balance` en memoria de Python. Un usuario con 1,500 monedas puede enviar 10 compras simultáneas de un ítem de 1,500 monedas; todas las transacciones leerán un saldo de 1,500, confirmarán la compra, y el usuario recibirá 10 ítems (valorados en 15,000 monedas) pagando solo 1,500.

---

### 3.3. Duplicación de Amuleto de Protección en Minería y Pesca
* **Archivos:** [minero.py](file:///c:/Users/Felipe/Desktop/Proyectos/Bot%20Discord/src/commands/economy/minero.py#L88-L94) y [pescador.py](file:///c:/Users/Felipe/Desktop/Proyectos/Bot%20Discord/src/commands/economy/pescador.py#L71-L74)
* **Gravedad:** **MEDIA 🟡**
* **Descripción:**
  El `Amuleto de Protección` (ID 7) salva al usuario de fallar en pesca y minería. La función de base de datos `usar_item_usuario` no comprueba si el `UPDATE` que resta el ítem realmente modificó filas (si `rowcount > 0`), sino que siempre retorna `True` si el usuario tenía el ítem inicialmente al hacer el `SELECT`. Un jugador con 1 solo amuleto puede jugar minería y pesca de forma paralela en dos canales y salvar ambos juegos de un derrumbe/rotura a la vez, consumiendo un solo amuleto.

---

### 3.4. Doble Uso de Tickets Consumibles en Slots
* **Archivo:** [slots.py](file:///c:/Users/Felipe/Desktop/Proyectos/Bot%20Discord/src/commands/casino/slots.py#L101-L105) y [db.py](file:///c:/Users/Felipe/Desktop/Proyectos/Bot%20Discord/src/db.py#L295-L326)
* **Gravedad:** **MEDIA 🟡**
* **Descripción:**
  El `Ticket de Suerte Slots` (ID 5) duplica las ganancias. Slots comprueba si el jugador lo tiene y luego llama a `usar_item_usuario`. Al igual que el amuleto de protección, la falta de validación en la actualización del inventario permite usar un mismo ticket en partidas simultáneas de slots y aplicar el multiplicador `2.0x` dos veces consumiendo solo un ticket.

---

### 3.5. Evasión del Escudo Anti-Mute por Ataques Paralelos
* **Archivo:** [specialmute.py](file:///c:/Users/Felipe/Desktop/Proyectos/Bot%20Discord/src/commands/moderation/specialmute.py)
* **Gravedad:** **MEDIA 🟡**
* **Descripción:**
  El `Escudo Anti-Mute` (ID 12) protege contra el `/specialmute`. Si tres atacantes se coordinan y lanzan el comando de muteo al mismo segundo contra la víctima, las tareas asíncronas consultarán el inventario de la víctima en paralelo, detectarán que tiene el escudo y procesarán la evasión. El escudo solo se restará una vez, bloqueando tres muteos simultáneos por el costo de un solo escudo.

---

## 🛠️ Plan de Mitigación y Soluciones Técnicas

Para solucionar estos problemas y evitar que los usuarios aprovechen las condiciones de carrera, se deben implementar las siguientes correcciones de código:

### 1. Deshabilitar botones de forma SÍNCRONA e Inmediata (Mines - N1)
En todo callback de botón que interactúe con balances o inventarios, la bandera de bloqueo (`self.game_over` o `self.accion_realizada`) debe modificarse de forma síncrona **antes de cualquier llamada con `await`**.

* **Ejemplo de Corrección en Mines (N1):**
```python
# Dentro de MineButton o CashoutButton
async def callback(self, interaction: discord.Interaction):
    view: MinesView = self.view
    if interaction.user.id != view.user_id or view.game_over: # <-- Validación inicial síncrona
        await interaction.response.send_message("¡Esta no es tu partida o ya terminó!", ephemeral=True)
        return
        
    view.game_over = True # <-- Bloqueo inmediato síncrono antes del defer/await
    await interaction.response.defer()
    await view.process_win(interaction)
```

---

### 2. Registro síncrono de jugadores en Lobbies (Ruleta Rusa - N2)
El registro de un jugador en la lista local de la View debe ocurrir de forma síncrona antes de cualquier await de base de datos. Si la transacción asíncrona falla (por ejemplo, saldo insuficiente), se remueve al jugador de la lista.

* **Ejemplo de Corrección en Ruleta Rusa (N2):**
```python
async def btn_join(self, interaction: discord.Interaction, button: discord.ui.Button):
    if interaction.user in self.players:
        await interaction.response.send_message("Ya estás en el juego.", ephemeral=True)
        return
        
    self.players.append(interaction.user) # <-- Registrar primero de forma síncrona
    
    success, balance = await asyncio.to_thread(deduct_balance, user_id, self.bet)
    if not success:
        self.players.remove(interaction.user) # <-- Revertir registro si falla la transacción
        await interaction.response.send_message("No tienes suficiente saldo.", ephemeral=True)
        return
```

---

### 3. Implementación de Cooldowns Nativos de Discord (N3)
Añadir sistemáticamente el decorador `@app_commands.checks.cooldown(...)` a todos los comandos económicos para mitigar el spam de llamadas a la base de datos.

```python
@app_commands.command(name="slots", description="Juega a las tragamonedas.")
@app_commands.checks.cooldown(1, 3.0, key=lambda i: i.user.id) # 1 uso cada 3 segundos por usuario
async def slots(self, interaction: discord.Interaction, apuesta: int):
    ...
```

---

### 4. Cooldown Diario Atómico en la Base de Datos (/daily - N4)
Evitar la validación de fecha en memoria de Python. Utilizar una consulta SQL `UPDATE ... WHERE` atómica y verificar si la fila se actualizó evaluando `cursor.rowcount`.

* **Ejemplo de Corrección en DB (N4):**
```python
def claim_daily(user_id):
    today = datetime.now().date()
    reward = 100 # ... lógica de racha ...
    with db_cursor() as cursor:
        cursor.execute("""
            UPDATE Users 
            SET LastLogin = %s, Balance = Balance + %s, Streak = Streak + 1
            WHERE UserID = %s AND (LastLogin IS NULL OR LastLogin < %s)
        """, (today, reward, user_id, today))
        
        if cursor.rowcount == 0:
            return False, 0 # Ya reclamado hoy
        return True, reward
```

---

### 5. Atomicidad en el Consumo de Energía (N5 y N6)
El consumo de energía de `/trabajo` debe ser atómico en una única sentencia SQL para evitar que se ejecuten múltiples trabajos concurrentes que superen el límite de energía.

* **Ejemplo de Corrección en Energia (N5):**
```python
def consumir_energia(user_id: int, cantidad: int) -> bool:
    with db_cursor() as cursor:
        cursor.execute("""
            UPDATE Users 
            SET Energia = Energia - %s 
            WHERE UserID = %s AND Energia >= %s
        """, (cantidad, user_id, cantidad))
        return cursor.rowcount > 0 # Retorna True si realmente se descontó
```

---

### 6. Verificación estricta en el uso de Ítems e Inventario (3.3 y 3.4)
En la función `usar_item_usuario` de `db.py`, verificar siempre que la cantidad de filas afectadas por la actualización sea mayor a cero, garantizando que el ítem realmente existiera y se consumió en la transacción.

* **Ejemplo de Corrección en uso de items (db.py):**
```python
def usar_item_usuario(user_id, item_id):
    with db_cursor() as cursor:
        cursor.execute("""
            UPDATE UserItems 
            SET Quantity = Quantity - 1,
                Used = CASE WHEN Quantity - 1 <= 0 THEN 1 ELSE Used END
            WHERE UserID = %s AND ItemID = %s AND Quantity > 0 AND Used = 0 
            AND Expiry = %s
        """, (user_id, item_id, expiry_date))
        return cursor.rowcount > 0 # <-- Validar si realmente se actualizó la fila
```

---

### 7. Ajuste del diseño del Ticket de Crash (3.1)
Para mitigar la anomalía matemática del ticket de Crash:
1. **Límite de Apuesta:** El ticket solo cubre reembolsos para apuestas de hasta un valor máximo de monedas (ej. `5,000`).
2. **Consumo por Uso:** El ticket se consume siempre al inicio de la ronda de crash por el solo hecho de usar el "seguro de protección", ganes o pierdas.
