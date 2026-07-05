# 📊 Análisis de Comandos y Sistema de Juego del Bot de Discord

Este documento contiene un análisis detallado, explicación y demostración del funcionamiento de **cada comando** y **módulo de trabajo** del bot, incluyendo sus parámetros, lógica de base de datos, reglas de negocio y flujos de interacción.

## 📈 Estadísticas Generales del Sistema

- **Total de Comandos Registrados:** 61
- **Categorías Analizadas:**
  - 📂 **Actions**: 4 comandos
  - 📂 **Casino**: 18 comandos
  - 📂 **Economy**: 11 comandos
  - 📂 **General**: 9 comandos
  - 📂 **Moderation**: 12 comandos
  - 📂 **Shop**: 7 comandos
  - 💼 **Trabajos Interactivos (Mini-juegos):** 11 especializaciones en el panel `/trabajo`

---

## 📂 Categoría: ACTIONS

Comandos y módulos de lógica en la carpeta `src/commands/actions`.

### 📄 Archivo: `actions\daily.py`

#### 🔹 Comando `/daily`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `daily()` en línea 11
- **Descripción:** Reclama tu recompensa diaria.

*Este comando no requiere parámetros adicionales.*

##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🗄️ Interacciones con Base de Datos / Servicios:
El comando realiza las siguientes llamadas a funciones de base de datos o servicios:
- `claim_daily`
- `ensure_user`


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario envía el comando en el canal de Discord.
 2. El bot difiere la respuesta (`defer()`) para operaciones lentas de base de datos.
 3. Se consulta y actualiza la base de datos de manera asíncrona mediante hilos de trabajo.
 4. El bot responde con un Embed de Discord con los detalles de la operación.

---

### 📄 Archivo: `actions\regalar.py`

#### 🔹 Comando `/regalar`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `regalar()` en línea 19
- **Descripción:** Regala dinero a otro usuario

| Parámetro | Tipo | Descripción | Requerido |
| :--- | :--- | :--- | :--- |
| `usuario` | `discord.Member` | El usuario al que quieres regalarle dinero | Sí |
| `cantidad` | `int` | Cantidad de monedas a regalar | Sí |


##### ⚙️ Lógica Interna y Validaciones:
- **Auto-transacción:** Evita que el usuario ejecute la acción sobre sí mismo.
- **Evitar Bots:** Restringe la acción si el usuario objetivo es un bot.
- **Monto Positivo:** Valida que la cantidad o apuesta sea mayor a 0.
- **Verificación de Saldo:** Consulta el balance del usuario antes de proceder para asegurar fondos suficientes.


##### 🗄️ Interacciones con Base de Datos / Servicios:
El comando realiza las siguientes llamadas a funciones de base de datos o servicios:
- `UserService.ensure_user`
- `UserService.get_balance`


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario ejecuta el comando y el bot valida los parámetros básicos.
 2. El bot envía un mensaje con un menú interactivo (botones o selección) solicitando confirmación o acción.
 3. Tras interactuar, el bot procesa el resultado de manera transaccional y actualiza los datos en segundo plano.
 4. Finalmente, edita el mensaje original para mostrar el resultado con un Embed coloreado (Verde para éxito, Rojo para error/cancelación).

---

### 📄 Archivo: `actions\robar.py`

#### 🔹 Comando `/perfil_ladron`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `perfil_ladron_cmd()` en línea 238
- **Descripción:** Muestra tu nivel, rango y bonificaciones como ladrón.

*Este comando no requiere parámetros adicionales.*

##### ⚙️ Lógica Interna y Validaciones:
- **Cooldown de Uso:** Tiene un límite de tiempo entre ejecuciones.


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario envía el comando en el canal de Discord.
 2. El bot difiere la respuesta (`defer()`) para operaciones lentas de base de datos.
 4. El bot responde con un Embed de Discord con los detalles de la operación.

---

#### 🔹 Comando `/robar`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `robar_slash()` en línea 318
- **Descripción:** Intenta robar dinero a otro usuario

| Parámetro | Tipo | Descripción | Requerido |
| :--- | :--- | :--- | :--- |
| `victima` | `discord.Member` | Usuario al que intentarás robar | Sí |


##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario envía el comando en el canal de Discord.
 2. El bot difiere la respuesta (`defer()`) para operaciones lentas de base de datos.
 4. El bot responde con un Embed de Discord con los detalles de la operación.

---

## 📂 Categoría: CASINO

Comandos y módulos de lógica en la carpeta `src/commands/casino`.

### 📄 Archivo: `casino\blackjack.py`

#### 🔹 Comando `/blackjack`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `blackjack()` en línea 246
- **Descripción:** Juega una partida de blackjack contra la casa

| Parámetro | Tipo | Descripción | Requerido |
| :--- | :--- | :--- | :--- |
| `apuesta` | `int` | Cantidad de monedas a apostar | Sí |


##### ⚙️ Lógica Interna y Validaciones:
- **Monto Positivo:** Valida que la cantidad o apuesta sea mayor a 0.


##### 🗄️ Interacciones con Base de Datos / Servicios:
El comando realiza las siguientes llamadas a funciones de base de datos o servicios:
- `ensure_user`
- `registrar_transaccion`
- `usuario_tiene_mejora`


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario ejecuta el comando y el bot valida los parámetros básicos.
 2. El bot envía un mensaje con un menú interactivo (botones o selección) solicitando confirmación o acción.
 3. Tras interactuar, el bot procesa el resultado de manera transaccional y actualiza los datos en segundo plano.
 4. Finalmente, edita el mensaje original para mostrar el resultado con un Embed coloreado (Verde para éxito, Rojo para error/cancelación).

---

### 📄 Archivo: `casino\casino_info.py`

#### 🔹 Comando `/casino`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `casino()` en línea 10
- **Descripción:** Muestra la información de los juegos disponibles en el casino.

*Este comando no requiere parámetros adicionales.*

##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario envía el comando en el canal de Discord.
 2. El bot difiere la respuesta (`defer()`) para operaciones lentas de base de datos.
 4. El bot responde con un Embed de Discord con los detalles de la operación.

---

### 📄 Archivo: `casino\casino_war.py`

#### 🔹 Comando `/casino_war`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `casino_war_cmd()` en línea 241
- **Descripción:** Juega Casino War. Si hay empate, decide si rendirte o ir a la Guerra.

*Este comando no requiere parámetros adicionales.*

##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario ejecuta el comando y el bot valida los parámetros básicos.
 2. El bot envía un mensaje con un menú interactivo (botones o selección) solicitando confirmación o acción.
 3. Tras interactuar, el bot procesa el resultado de manera transaccional y actualiza los datos en segundo plano.
 4. Finalmente, edita el mensaje original para mostrar el resultado con un Embed coloreado (Verde para éxito, Rojo para error/cancelación).

---

### 📄 Archivo: `casino\coinflip.py`

#### 🔹 Comando `/coinflip`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `coinflip()` en línea 313
- **Descripción:** Juega un coinflip: elige cara o sello con los botones

| Parámetro | Tipo | Descripción | Requerido |
| :--- | :--- | :--- | :--- |
| `apuesta` | `int` | Cantidad de monedas a apostar | Sí |
| `retar` | `Optional[discord.Member]` | Usuario al que quieres retar a un duelo (opcional) | No |


##### ⚙️ Lógica Interna y Validaciones:
- **Monto Positivo:** Valida que la cantidad o apuesta sea mayor a 0.
- **Verificación de Saldo:** Consulta el balance del usuario antes de proceder para asegurar fondos suficientes.


##### 🗄️ Interacciones con Base de Datos / Servicios:
El comando realiza las siguientes llamadas a funciones de base de datos o servicios:
- `ensure_user`
- `get_balance`


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario ejecuta el comando y el bot valida los parámetros básicos.
 2. El bot envía un mensaje con un menú interactivo (botones o selección) solicitando confirmación o acción.
 3. Tras interactuar, el bot procesa el resultado de manera transaccional y actualiza los datos en segundo plano.
 4. Finalmente, edita el mensaje original para mostrar el resultado con un Embed coloreado (Verde para éxito, Rojo para error/cancelación).

---

### 📄 Archivo: `casino\crash.py`

#### 🔹 Comando `/crash`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `crash_slash()` en línea 17
- **Descripción:** Juega Crash: apuesta y retírate antes de que el multiplicador explote!

| Parámetro | Tipo | Descripción | Requerido |
| :--- | :--- | :--- | :--- |
| `apuesta` | `int` | Cantidad de monedas a apostar | Sí |


##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario envía el comando en el canal de Discord.
 2. El bot difiere la respuesta (`defer()`) para operaciones lentas de base de datos.
 4. El bot responde con un Embed de Discord con los detalles de la operación.

---

### 📄 Archivo: `casino\higher_lower.py`

#### 🔹 Comando `/higherlow`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `higher_lower_slash()` en línea 369
- **Descripción:** Juega Higher or Lower: predice si la siguiente carta será mayor o menor

| Parámetro | Tipo | Descripción | Requerido |
| :--- | :--- | :--- | :--- |
| `apuesta` | `int` | Cantidad de monedas a apostar | Sí |


##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario envía el comando en el canal de Discord.
 2. El bot difiere la respuesta (`defer()`) para operaciones lentas de base de datos.
 4. El bot responde con un Embed de Discord con los detalles de la operación.

---

### 📄 Archivo: `casino\horse_race.py`

#### 🔹 Comando `/horse_race`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `horse_race()` en línea 298
- **Descripción:** Organiza una carrera de caballos multijugador.

*Este comando no requiere parámetros adicionales.*

##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario ejecuta el comando y el bot valida los parámetros básicos.
 2. El bot envía un mensaje con un menú interactivo (botones o selección) solicitando confirmación o acción.
 3. Tras interactuar, el bot procesa el resultado de manera transaccional y actualiza los datos en segundo plano.
 4. Finalmente, edita el mensaje original para mostrar el resultado con un Embed coloreado (Verde para éxito, Rojo para error/cancelación).

---

### 📄 Archivo: `casino\liars_dice.py`

#### 🔹 Comando `/liars_dice`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `liars_dice_cmd()` en línea 330
- **Descripción:** Abre una mesa de Dados de Mentiroso (Multijugador).

| Parámetro | Tipo | Descripción | Requerido |
| :--- | :--- | :--- | :--- |
| `apuesta` | `int` | Cantidad a apostar para entrar a la mesa | Sí |


##### ⚙️ Lógica Interna y Validaciones:
- **Monto Positivo:** Valida que la cantidad o apuesta sea mayor a 0.


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario ejecuta el comando y el bot valida los parámetros básicos.
 2. El bot envía un mensaje con un menú interactivo (botones o selección) solicitando confirmación o acción.
 3. Tras interactuar, el bot procesa el resultado de manera transaccional y actualiza los datos en segundo plano.
 4. Finalmente, edita el mensaje original para mostrar el resultado con un Embed coloreado (Verde para éxito, Rojo para error/cancelación).

---

### 📄 Archivo: `casino\loto.py`

#### 🔹 Comando `/loto`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `loto()` en línea 33
- **Descripción:** Muestra el pozo acumulado del loto del casino y tus boletos comprados hoy.

*Este comando no requiere parámetros adicionales.*

##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🗄️ Interacciones con Base de Datos / Servicios:
El comando realiza las siguientes llamadas a funciones de base de datos o servicios:
- `ensure_user`


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario envía el comando en el canal de Discord.
 2. El bot difiere la respuesta (`defer()`) para operaciones lentas de base de datos.
 3. Se consulta y actualiza la base de datos de manera asíncrona mediante hilos de trabajo.
 4. El bot responde con un Embed de Discord con los detalles de la operación.

---

#### 🔹 Comando `/loto_comprar`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `loto_comprar()` en línea 92
- **Descripción:** Compra un boleto de loto. Selecciona 4 números del 1 al 25.

| Parámetro | Tipo | Descripción | Requerido |
| :--- | :--- | :--- | :--- |
| `num1` | `Optional[int]` | Primer número (1-25) - Dejar vacío para autocompletar aleatoriamente | No |
| `num2` | `Optional[int]` | Segundo número (1-25) - Dejar vacío para autocompletar aleatoriamente | No |
| `num3` | `Optional[int]` | Tercer número (1-25) - Dejar vacío para autocompletar aleatoriamente | No |
| `num4` | `Optional[int]` | Cuarto número (1-25) - Dejar vacío para autocompletar aleatoriamente | No |


##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🗄️ Interacciones con Base de Datos / Servicios:
El comando realiza las siguientes llamadas a funciones de base de datos o servicios:
- `ensure_user`


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario envía el comando en el canal de Discord.
 2. El bot difiere la respuesta (`defer()`) para operaciones lentas de base de datos.
 3. Se consulta y actualiza la base de datos de manera asíncrona mediante hilos de trabajo.
 4. El bot responde con un Embed de Discord con los detalles de la operación.

---

#### 🔹 Comando `/loto_draw`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `loto_draw()` en línea 148
- **Descripción:** [ADMIN] Fuerza el sorteo del loto de forma manual e inmediata.

*Este comando no requiere parámetros adicionales.*

##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario envía el comando en el canal de Discord.
 2. El bot difiere la respuesta (`defer()`) para operaciones lentas de base de datos.
 4. El bot responde con un Embed de Discord con los detalles de la operación.

---

### 📄 Archivo: `casino\mines.py`

#### 🔹 Comando `/mines`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `mines()` en línea 389
- **Descripción:** Juega al Buscaminas. Encuentra diamantes y evita las bombas.

| Parámetro | Tipo | Descripción | Requerido |
| :--- | :--- | :--- | :--- |
| `apuesta` | `int` | Cantidad a apostar | Sí |


##### ⚙️ Lógica Interna y Validaciones:
- **Monto Positivo:** Valida que la cantidad o apuesta sea mayor a 0.


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario ejecuta el comando y el bot valida los parámetros básicos.
 2. El bot envía un mensaje con un menú interactivo (botones o selección) solicitando confirmación o acción.
 3. Tras interactuar, el bot procesa el resultado de manera transaccional y actualiza los datos en segundo plano.
 4. Finalmente, edita el mensaje original para mostrar el resultado con un Embed coloreado (Verde para éxito, Rojo para error/cancelación).

---

### 📄 Archivo: `casino\plinko.py`

#### 🔹 Comando `/plinko`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `plinko_cmd()` en línea 230
- **Descripción:** Juega al clásico Plinko con multiplicadores variables.

*Este comando no requiere parámetros adicionales.*

##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario ejecuta el comando y el bot valida los parámetros básicos.
 2. El bot envía un mensaje con un menú interactivo (botones o selección) solicitando confirmación o acción.
 3. Tras interactuar, el bot procesa el resultado de manera transaccional y actualiza los datos en segundo plano.
 4. Finalmente, edita el mensaje original para mostrar el resultado con un Embed coloreado (Verde para éxito, Rojo para error/cancelación).

---

### 📄 Archivo: `casino\provably_fair_cmd.py`

#### 🔹 Comando `/provably_fair`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `provably_fair_cmd()` en línea 12
- **Descripción:** Verifica la transparencia de tus juegos de casino.

*Este comando no requiere parámetros adicionales.*

##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario ejecuta el comando y el bot valida los parámetros básicos.
 2. El bot envía un mensaje con un menú interactivo (botones o selección) solicitando confirmación o acción.
 3. Tras interactuar, el bot procesa el resultado de manera transaccional y actualiza los datos en segundo plano.
 4. Finalmente, edita el mensaje original para mostrar el resultado con un Embed coloreado (Verde para éxito, Rojo para error/cancelación).

---

### 📄 Archivo: `casino\roulette.py`

#### 🔹 Comando `/roulette`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `roulette()` en línea 161
- **Descripción:** Juega a la Ruleta Europea.

| Parámetro | Tipo | Descripción | Requerido |
| :--- | :--- | :--- | :--- |
| `apuesta` | `int` | Cantidad de monedas a apostar | Sí |


##### ⚙️ Lógica Interna y Validaciones:
- **Monto Positivo:** Valida que la cantidad o apuesta sea mayor a 0.


##### 🗄️ Interacciones con Base de Datos / Servicios:
El comando realiza las siguientes llamadas a funciones de base de datos o servicios:
- `ensure_user`


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario ejecuta el comando y el bot valida los parámetros básicos.
 2. El bot envía un mensaje con un menú interactivo (botones o selección) solicitando confirmación o acción.
 3. Tras interactuar, el bot procesa el resultado de manera transaccional y actualiza los datos en segundo plano.
 4. Finalmente, edita el mensaje original para mostrar el resultado con un Embed coloreado (Verde para éxito, Rojo para error/cancelación).

---

### 📄 Archivo: `casino\rps_bet.py`

#### 🔹 Comando `/rps_bet`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `rps_bet()` en línea 229
- **Descripción:** Reta a otro usuario a un duelo de Piedra, Papel o Tijera por dinero.

| Parámetro | Tipo | Descripción | Requerido |
| :--- | :--- | :--- | :--- |
| `oponente` | `discord.Member` | Usuario al que quieres retar | Sí |
| `apuesta` | `int` | Cantidad de monedas a apostar | Sí |


##### ⚙️ Lógica Interna y Validaciones:
- **Monto Positivo:** Valida que la cantidad o apuesta sea mayor a 0.


##### 🗄️ Interacciones con Base de Datos / Servicios:
El comando realiza las siguientes llamadas a funciones de base de datos o servicios:
- `ensure_user`


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario ejecuta el comando y el bot valida los parámetros básicos.
 2. El bot envía un mensaje con un menú interactivo (botones o selección) solicitando confirmación o acción.
 3. Tras interactuar, el bot procesa el resultado de manera transaccional y actualiza los datos en segundo plano.
 4. Finalmente, edita el mensaje original para mostrar el resultado con un Embed coloreado (Verde para éxito, Rojo para error/cancelación).

---

### 📄 Archivo: `casino\russian_roulette.py`

#### 🔹 Comando `/russian_roulette`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `russian_roulette()` en línea 210
- **Descripción:** Organiza un juego de Ruleta Rusa de Apuestas.

| Parámetro | Tipo | Descripción | Requerido |
| :--- | :--- | :--- | :--- |
| `entrada` | `int` | Cantidad de monedas para entrar al juego | Sí |


##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🗄️ Interacciones con Base de Datos / Servicios:
El comando realiza las siguientes llamadas a funciones de base de datos o servicios:
- `ensure_user`


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario ejecuta el comando y el bot valida los parámetros básicos.
 2. El bot envía un mensaje con un menú interactivo (botones o selección) solicitando confirmación o acción.
 3. Tras interactuar, el bot procesa el resultado de manera transaccional y actualiza los datos en segundo plano.
 4. Finalmente, edita el mensaje original para mostrar el resultado con un Embed coloreado (Verde para éxito, Rojo para error/cancelación).

---

### 📄 Archivo: `casino\slots.py`

#### 🔹 Comando `/slots`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `slots()` en línea 16
- **Descripción:** Juega a las tragamonedas y prueba tu suerte.

| Parámetro | Tipo | Descripción | Requerido |
| :--- | :--- | :--- | :--- |
| `apuesta` | `int` | Cantidad a apostar | Sí |


##### ⚙️ Lógica Interna y Validaciones:
- **Monto Positivo:** Valida que la cantidad o apuesta sea mayor a 0.


##### 🗄️ Interacciones con Base de Datos / Servicios:
El comando realiza las siguientes llamadas a funciones de base de datos o servicios:
- `ensure_user`
- `usuario_tiene_mejora`


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario envía el comando en el canal de Discord.
 2. El bot difiere la respuesta (`defer()`) para operaciones lentas de base de datos.
 3. Se consulta y actualiza la base de datos de manera asíncrona mediante hilos de trabajo.
 4. El bot responde con un Embed de Discord con los detalles de la operación.

---

## 📂 Categoría: ECONOMY

Comandos y módulos de lógica en la carpeta `src/commands/economy`.

### 📄 Archivo: `economy\energia.py`

#### 🔹 Comando `/energia`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `energia_command()` en línea 36
- **Descripción:** Ver tu estado de energía actual

*Este comando no requiere parámetros adicionales.*

##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🗄️ Interacciones con Base de Datos / Servicios:
El comando realiza las siguientes llamadas a funciones de base de datos o servicios:
- `UserService.ensure_user`


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario envía el comando en el canal de Discord.
 2. El bot difiere la respuesta (`defer()`) para operaciones lentas de base de datos.
 3. Se consulta y actualiza la base de datos de manera asíncrona mediante hilos de trabajo.
 4. El bot responde con un Embed de Discord con los detalles de la operación.

---

#### 🔹 Comando `/energia_debug`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `energia_debug()` en línea 111
- **Descripción:** Información de debug del sistema de energía

| Parámetro | Tipo | Descripción | Requerido |
| :--- | :--- | :--- | :--- |
| `usuario` | `Optional[discord.Member]` | Sin descripción | No |


##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🗄️ Interacciones con Base de Datos / Servicios:
El comando realiza las siguientes llamadas a funciones de base de datos o servicios:
- `get_energia`


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario envía el comando en el canal de Discord.
 2. El bot difiere la respuesta (`defer()`) para operaciones lentas de base de datos.
 3. Se consulta y actualiza la base de datos de manera asíncrona mediante hilos de trabajo.
 4. El bot responde con un Embed de Discord con los detalles de la operación.

---

### 📄 Archivo: `economy\pets.py`

#### 🔹 Comando `/pets`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `pets_cmd()` en línea 369
- **Descripción:** Muestra tu colección de mascotas con sus características y lealtad.

*Este comando no requiere parámetros adicionales.*

##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario envía el comando en el canal de Discord.
 2. El bot difiere la respuesta (`defer()`) para operaciones lentas de base de datos.
 4. El bot responde con un Embed de Discord con los detalles de la operación.

---

#### 🔹 Comando `/pet_equipar`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `pet_equipar_cmd()` en línea 502
- **Descripción:** Equipa una mascota de tu colección usando su ID.

| Parámetro | Tipo | Descripción | Requerido |
| :--- | :--- | :--- | :--- |
| `pet_id` | `int` | Sin descripción | Sí |


##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario envía el comando en el canal de Discord.
 2. El bot difiere la respuesta (`defer()`) para operaciones lentas de base de datos.
 4. El bot responde con un Embed de Discord con los detalles de la operación.

---

#### 🔹 Comando `/pets_equipar`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `pets_equipar_cmd()` en línea 522
- **Descripción:** Equipa una mascota de tu colección usando su ID. (Alias de /pet_equipar)

| Parámetro | Tipo | Descripción | Requerido |
| :--- | :--- | :--- | :--- |
| `pet_id` | `int` | Sin descripción | Sí |


##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario envía el comando en el canal de Discord.
 2. El bot difiere la respuesta (`defer()`) para operaciones lentas de base de datos.
 4. El bot responde con un Embed de Discord con los detalles de la operación.

---

#### 🔹 Comando `/pet_nombre`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `pet_nombre_cmd()` en línea 527
- **Descripción:** Ponle un nombre personalizado a una de tus mascotas.

| Parámetro | Tipo | Descripción | Requerido |
| :--- | :--- | :--- | :--- |
| `pet_id` | `int` | ID de la mascota (visible en /pets) | Sí |
| `nombre` | `Optional[str]` | Nombre personalizado (máx. 32 caracteres) | No |
| `quitar` | `bool` | Quita el nombre personalizado y vuelve al nombre de la especie | Sí |


##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario envía el comando en el canal de Discord.
 2. El bot difiere la respuesta (`defer()`) para operaciones lentas de base de datos.
 4. El bot responde con un Embed de Discord con los detalles de la operación.

---

#### 🔹 Comando `/pets_nombre`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `pets_nombre_cmd()` en línea 551
- **Descripción:** Ponle un nombre personalizado a una de tus mascotas. (Alias de /pet_nombre)

| Parámetro | Tipo | Descripción | Requerido |
| :--- | :--- | :--- | :--- |
| `pet_id` | `int` | ID de la mascota (visible en /pets) | Sí |
| `nombre` | `Optional[str]` | Nombre personalizado (máx. 32 caracteres) | No |
| `quitar` | `bool` | Quita el nombre personalizado y vuelve al nombre de la especie | Sí |


##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario envía el comando en el canal de Discord.
 2. El bot difiere la respuesta (`defer()`) para operaciones lentas de base de datos.
 4. El bot responde con un Embed de Discord con los detalles de la operación.

---

#### 🔹 Comando `/apostador`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `apostador_cmd()` en línea 555
- **Descripción:** Muestra tu progreso y Nivel de Apostador.

*Este comando no requiere parámetros adicionales.*

##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario envía el comando en el canal de Discord.
 2. El bot difiere la respuesta (`defer()`) para operaciones lentas de base de datos.
 4. El bot responde con un Embed de Discord con los detalles de la operación.

---

### 📄 Archivo: `economy\plata.py`

#### 🔹 Comando `/plata`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `plata()` en línea 23
- **Descripción:** Consulta tu balance o el de otro usuario.

| Parámetro | Tipo | Descripción | Requerido |
| :--- | :--- | :--- | :--- |
| `usuario` | `discord.Member` | Usuario a consultar (opcional) | Sí |


##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario envía el comando en el canal de Discord.
 2. El bot difiere la respuesta (`defer()`) para operaciones lentas de base de datos.
 4. El bot responde con un Embed de Discord con los detalles de la operación.

---

#### 🔹 Comando `/crear_plata`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `crear_plata()` en línea 47
- **Descripción:** Genera dinero por si se buguean cosas (Solo Administrador).

| Parámetro | Tipo | Descripción | Requerido |
| :--- | :--- | :--- | :--- |
| `cantidad` | `int` | Cantidad de dinero a generar | Sí |
| `usuario` | `discord.Member` | Usuario que recibirá el dinero (opcional) | Sí |


##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario envía el comando en el canal de Discord.
 2. El bot difiere la respuesta (`defer()`) para operaciones lentas de base de datos.
 4. El bot responde con un Embed de Discord con los detalles de la operación.

---

### 📄 Archivo: `economy\trabajo.py`

#### 🔹 Comando `/trabajo`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `trabajo()` en línea 397
- **Descripción:** Explora los trabajos disponibles y gana dinero

*Este comando no requiere parámetros adicionales.*

##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario ejecuta el comando y el bot valida los parámetros básicos.
 2. El bot envía un mensaje con un menú interactivo (botones o selección) solicitando confirmación o acción.
 3. Tras interactuar, el bot procesa el resultado de manera transaccional y actualiza los datos en segundo plano.
 4. Finalmente, edita el mensaje original para mostrar el resultado con un Embed coloreado (Verde para éxito, Rojo para error/cancelación).

---

## 📂 Categoría: GENERAL

Comandos y módulos de lógica en la carpeta `src/commands/general`.

### 📄 Archivo: `general\avatar.py`

#### 🔹 Comando `/avatar`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `avatar()` en línea 10
- **Descripción:** Muestra el avatar de un usuario.

| Parámetro | Tipo | Descripción | Requerido |
| :--- | :--- | :--- | :--- |
| `member` | `discord.Member` | Usuario del que quieres ver el avatar | Sí |


##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario envía el comando en el canal de Discord.
 2. El bot difiere la respuesta (`defer()`) para operaciones lentas de base de datos.
 4. El bot responde con un Embed de Discord con los detalles de la operación.

---

### 📄 Archivo: `general\botinfo.py`

#### 🔹 Comando `/botinfo`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `botinfo()` en línea 9
- **Descripción:** Muestra información sobre el bot.

*Este comando no requiere parámetros adicionales.*

##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario envía el comando en el canal de Discord.
 2. El bot difiere la respuesta (`defer()`) para operaciones lentas de base de datos.
 4. El bot responde con un Embed de Discord con los detalles de la operación.

---

### 📄 Archivo: `general\difficulty_stats.py`

#### 🔹 Comando `/stats`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `stats()` en línea 13
- **Descripción:** Ver tus estadísticas de juego y nivel de dificultad actual

*Este comando no requiere parámetros adicionales.*

##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🗄️ Interacciones con Base de Datos / Servicios:
El comando realiza las siguientes llamadas a funciones de base de datos o servicios:
- `UserService.ensure_user`


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario envía el comando en el canal de Discord.
 2. El bot difiere la respuesta (`defer()`) para operaciones lentas de base de datos.
 3. Se consulta y actualiza la base de datos de manera asíncrona mediante hilos de trabajo.
 4. El bot responde con un Embed de Discord con los detalles de la operación.

---

#### 🔹 Comando `/difficulty`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `difficulty_info()` en línea 153
- **Descripción:** Ver información detallada sobre el sistema de dificultad

*Este comando no requiere parámetros adicionales.*

##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario envía el comando en el canal de Discord.
 2. El bot difiere la respuesta (`defer()`) para operaciones lentas de base de datos.
 4. El bot responde con un Embed de Discord con los detalles de la operación.

---

### 📄 Archivo: `general\historial.py`

#### 🔹 Comando `/historial`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `historial()` en línea 13
- **Descripción:** Muestra el historial de transacciones recientes de un usuario.

| Parámetro | Tipo | Descripción | Requerido |
| :--- | :--- | :--- | :--- |
| `usuario` | `discord.Member` | Usuario a consultar (opcional) | Sí |


##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🗄️ Interacciones con Base de Datos / Servicios:
El comando realiza las siguientes llamadas a funciones de base de datos o servicios:
- `ensure_user`


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario envía el comando en el canal de Discord.
 2. El bot difiere la respuesta (`defer()`) para operaciones lentas de base de datos.
 3. Se consulta y actualiza la base de datos de manera asíncrona mediante hilos de trabajo.
 4. El bot responde con un Embed de Discord con los detalles de la operación.

---

### 📄 Archivo: `general\serverinfo.py`

#### 🔹 Comando `/serverinfo`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `serverinfo()` en línea 9
- **Descripción:** Muestra información del servidor.

*Este comando no requiere parámetros adicionales.*

##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario envía el comando en el canal de Discord.
 2. El bot difiere la respuesta (`defer()`) para operaciones lentas de base de datos.
 4. El bot responde con un Embed de Discord con los detalles de la operación.

---

### 📄 Archivo: `general\top.py`

#### 🔹 Comando `/top`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `top()` en línea 14
- **Descripción:** Muestra el top de usuarios con más monedas en el servidor.

*Este comando no requiere parámetros adicionales.*

##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🗄️ Interacciones con Base de Datos / Servicios:
El comando realiza las siguientes llamadas a funciones de base de datos o servicios:
- `UserService.ensure_user`


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario envía el comando en el canal de Discord.
 2. El bot difiere la respuesta (`defer()`) para operaciones lentas de base de datos.
 3. Se consulta y actualiza la base de datos de manera asíncrona mediante hilos de trabajo.
 4. El bot responde con un Embed de Discord con los detalles de la operación.

---

#### 🔹 Comando `/top_minas`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `top_minas()` en línea 83
- **Descripción:** Muestra el top de usuarios que más minas han pisado en el servidor.

*Este comando no requiere parámetros adicionales.*

##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🗄️ Interacciones con Base de Datos / Servicios:
El comando realiza las siguientes llamadas a funciones de base de datos o servicios:
- `UserService.ensure_user`


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario envía el comando en el canal de Discord.
 2. El bot difiere la respuesta (`defer()`) para operaciones lentas de base de datos.
 3. Se consulta y actualiza la base de datos de manera asíncrona mediante hilos de trabajo.
 4. El bot responde con un Embed de Discord con los detalles de la operación.

---

### 📄 Archivo: `general\userinfo.py`

#### 🔹 Comando `/userinfo`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `userinfo()` en línea 10
- **Descripción:** Muestra información de un usuario.

| Parámetro | Tipo | Descripción | Requerido |
| :--- | :--- | :--- | :--- |
| `member` | `discord.Member` | Usuario del que quieres ver la información | Sí |


##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario envía el comando en el canal de Discord.
 2. El bot difiere la respuesta (`defer()`) para operaciones lentas de base de datos.
 4. El bot responde con un Embed de Discord con los detalles de la operación.

---

## 📂 Categoría: MODERATION

Comandos y módulos de lógica en la carpeta `src/commands/moderation`.

### 📄 Archivo: `moderation\mensaje.py`

#### 🔹 Comando `/mensaje`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `mensaje()` en línea 17
- **Descripción:** Envía un mensaje como el bot (solo owner)

| Parámetro | Tipo | Descripción | Requerido |
| :--- | :--- | :--- | :--- |
| `contenido` | `str` | El contenido del mensaje que quieres enviar | Sí |
| `canal` | `Optional[discord.TextChannel]` | Canal donde enviar el mensaje (opcional, por defecto el actual) | No |


##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario envía el comando en el canal de Discord.
 2. El bot difiere la respuesta (`defer()`) para operaciones lentas de base de datos.
 4. El bot responde con un Embed de Discord con los detalles de la operación.

---

#### 🔹 Comando `/embed`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `embed()` en línea 76
- **Descripción:** Envía un embed como el bot (solo owner)

| Parámetro | Tipo | Descripción | Requerido |
| :--- | :--- | :--- | :--- |
| `titulo` | `str` | Título del embed | Sí |
| `descripcion` | `str` | Descripción del embed | Sí |
| `color` | `Optional[str]` | Color del embed (hex, ej: #ff0000 para rojo) | No |
| `canal` | `Optional[discord.TextChannel]` | Canal donde enviar el embed (opcional, por defecto el actual) | No |


##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario envía el comando en el canal de Discord.
 2. El bot difiere la respuesta (`defer()`) para operaciones lentas de base de datos.
 4. El bot responde con un Embed de Discord con los detalles de la operación.

---

### 📄 Archivo: `moderation\minas.py`

#### 🔹 Comando `/poner_minas`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `poner_minas()` en línea 31
- **Descripción:** Coloca minas explosivas ocultas en un canal específico.

| Parámetro | Tipo | Descripción | Requerido |
| :--- | :--- | :--- | :--- |
| `cantidad` | `int` | Número de minas a colocar | Sí |
| `canal` | `discord.TextChannel` | El canal donde se colocarán las minas | Sí |


##### ⚙️ Lógica Interna y Validaciones:
- **Monto Positivo:** Valida que la cantidad o apuesta sea mayor a 0.


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario envía el comando en el canal de Discord.
 2. El bot difiere la respuesta (`defer()`) para operaciones lentas de base de datos.
 4. El bot responde con un Embed de Discord con los detalles de la operación.

---

#### 🔹 Comando `/sacar_minas`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `sacar_minas()` en línea 130
- **Descripción:** Elimina todas las minas de un canal específico.

| Parámetro | Tipo | Descripción | Requerido |
| :--- | :--- | :--- | :--- |
| `canal` | `discord.TextChannel` | El canal donde se eliminarán las minas (opcional, por defecto el canal actual) | Sí |


##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario envía el comando en el canal de Discord.
 2. El bot difiere la respuesta (`defer()`) para operaciones lentas de base de datos.
 4. El bot responde con un Embed de Discord con los detalles de la operación.

---

#### 🔹 Comando `/info_minas`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `info_minas()` en línea 151
- **Descripción:** Muestra la información de las minas en un canal específico.

| Parámetro | Tipo | Descripción | Requerido |
| :--- | :--- | :--- | :--- |
| `canal` | `discord.TextChannel` | El canal del que quieres ver la información (opcional, por defecto el canal actual) | Sí |


##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario envía el comando en el canal de Discord.
 2. El bot difiere la respuesta (`defer()`) para operaciones lentas de base de datos.
 4. El bot responde con un Embed de Discord con los detalles de la operación.

---

### 📄 Archivo: `moderation\mute.py`

#### 🔹 Comando `/mute`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `mute()` en línea 12
- **Descripción:** Silencia a un usuario en el servidor.

| Parámetro | Tipo | Descripción | Requerido |
| :--- | :--- | :--- | :--- |
| `miembro` | `discord.Member` | Usuario a silenciar | Sí |
| `motivo` | `str` | Motivo del silencio | Sí |


##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario envía el comando en el canal de Discord.
 2. El bot difiere la respuesta (`defer()`) para operaciones lentas de base de datos.
 4. El bot responde con un Embed de Discord con los detalles de la operación.

---

### 📄 Archivo: `moderation\poll.py`

#### 🔹 Comando `/poll`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `poll()` en línea 163
- **Descripción:** Crear una votación interactiva

| Parámetro | Tipo | Descripción | Requerido |
| :--- | :--- | :--- | :--- |
| `pregunta` | `str` | La pregunta de la votación | Sí |
| `opcion1` | `str` | Primera opción | Sí |
| `opcion2` | `str` | Segunda opción | Sí |
| `opcion3` | `Optional[str]` | Tercera opción (opcional) | No |
| `opcion4` | `Optional[str]` | Cuarta opción (opcional) | No |
| `opcion5` | `Optional[str]` | Quinta opción (opcional) | No |
| `duracion` | `Optional[int]` | Duración en minutos (por defecto 5 minutos) | No |


##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario ejecuta el comando y el bot valida los parámetros básicos.
 2. El bot envía un mensaje con un menú interactivo (botones o selección) solicitando confirmación o acción.
 3. Tras interactuar, el bot procesa el resultado de manera transaccional y actualiza los datos en segundo plano.
 4. Finalmente, edita el mensaje original para mostrar el resultado con un Embed coloreado (Verde para éxito, Rojo para error/cancelación).

---

#### 🔹 Comando `/poll_simple`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `poll_simple()` en línea 225
- **Descripción:** Crear una votación simple Sí/No

| Parámetro | Tipo | Descripción | Requerido |
| :--- | :--- | :--- | :--- |
| `pregunta` | `str` | La pregunta de la votación | Sí |
| `duracion` | `Optional[int]` | Duración en minutos (por defecto 5 minutos) | No |


##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario ejecuta el comando y el bot valida los parámetros básicos.
 2. El bot envía un mensaje con un menú interactivo (botones o selección) solicitando confirmación o acción.
 3. Tras interactuar, el bot procesa el resultado de manera transaccional y actualiza los datos en segundo plano.
 4. Finalmente, edita el mensaje original para mostrar el resultado con un Embed coloreado (Verde para éxito, Rojo para error/cancelación).

---

### 📄 Archivo: `moderation\purge.py`

#### 🔹 Comando `/purge`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `purge()` en línea 12
- **Descripción:** Elimina una cantidad de mensajes del canal actual.

| Parámetro | Tipo | Descripción | Requerido |
| :--- | :--- | :--- | :--- |
| `amount` | `int` | Cantidad de mensajes a eliminar (1-100) | Sí |


##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario envía el comando en el canal de Discord.
 2. El bot difiere la respuesta (`defer()`) para operaciones lentas de base de datos.
 4. El bot responde con un Embed de Discord con los detalles de la operación.

---

### 📄 Archivo: `moderation\slowmode.py`

#### 🔹 Comando `/slowmode`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `slowmode()` en línea 12
- **Descripción:** Establece el slowmode del canal actual (en segundos).

| Parámetro | Tipo | Descripción | Requerido |
| :--- | :--- | :--- | :--- |
| `seconds` | `int` | Cantidad de segundos para el slowmode (0 para desactivar, máx 21600) | Sí |


##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario envía el comando en el canal de Discord.
 2. El bot difiere la respuesta (`defer()`) para operaciones lentas de base de datos.
 4. El bot responde con un Embed de Discord con los detalles de la operación.

---

### 📄 Archivo: `moderation\specialmute.py`

#### 🔹 Comando `/specialmute`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `specialmute()` en línea 43
- **Descripción:** Mutea a un usuario aleatoriamente (solo mención, no ID).

| Parámetro | Tipo | Descripción | Requerido |
| :--- | :--- | :--- | :--- |
| `miembro` | `discord.Member` | Usuario a mutear (selecciónalo del menú o menciónalo) | Sí |


##### ⚙️ Lógica Interna y Validaciones:
- **Cooldown de Uso:** Tiene un límite de tiempo entre ejecuciones.


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario envía el comando en el canal de Discord.
 2. El bot difiere la respuesta (`defer()`) para operaciones lentas de base de datos.
 4. El bot responde con un Embed de Discord con los detalles de la operación.

---

### 📄 Archivo: `moderation\unmute.py`

#### 🔹 Comando `/unmute`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `unmute()` en línea 12
- **Descripción:** Quita el silencio a un usuario en el servidor.

| Parámetro | Tipo | Descripción | Requerido |
| :--- | :--- | :--- | :--- |
| `miembro` | `discord.Member` | Usuario a desmutear | Sí |


##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario envía el comando en el canal de Discord.
 2. El bot difiere la respuesta (`defer()`) para operaciones lentas de base de datos.
 4. El bot responde con un Embed de Discord con los detalles de la operación.

---

## 📂 Categoría: SHOP

Comandos y módulos de lógica en la carpeta `src/commands/shop`.

### 📄 Archivo: `shop\blackmarket.py`

#### 🔹 Comando `/blackmarket`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `blackmarket()` en línea 56
- **Descripción:** Muestra las mejoras permanentes del mercado negro.

*Este comando no requiere parámetros adicionales.*

##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario envía el comando en el canal de Discord.
 2. El bot difiere la respuesta (`defer()`) para operaciones lentas de base de datos.
 4. El bot responde con un Embed de Discord con los detalles de la operación.

---

#### 🔹 Comando `/dopear_caballo`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `dopear_caballo()` en línea 74
- **Descripción:** [MERCADO NEGRO] Inyecta sustancias a un caballo para su próxima carrera (Costo: 5000).

*Este comando no requiere parámetros adicionales.*

##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario ejecuta el comando y el bot valida los parámetros básicos.
 2. El bot envía un mensaje con un menú interactivo (botones o selección) solicitando confirmación o acción.
 3. Tras interactuar, el bot procesa el resultado de manera transaccional y actualiza los datos en segundo plano.
 4. Finalmente, edita el mensaje original para mostrar el resultado con un Embed coloreado (Verde para éxito, Rojo para error/cancelación).

---

### 📄 Archivo: `shop\comprar_mejora.py`

#### 🔹 Comando `/comprar_mejora`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `comprar_mejora()` en línea 37
- **Descripción:** Compra una mejora permanente del black market por su ID.

| Parámetro | Tipo | Descripción | Requerido |
| :--- | :--- | :--- | :--- |
| `mejora_id` | `int` | ID de la mejora a comprar | Sí |


##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario envía el comando en el canal de Discord.
 2. El bot difiere la respuesta (`defer()`) para operaciones lentas de base de datos.
 4. El bot responde con un Embed de Discord con los detalles de la operación.

---

### 📄 Archivo: `shop\tienda.py`

#### 🔹 Comando `/tienda`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `tienda()` en línea 82
- **Descripción:** Muestra los artículos consumibles de un solo uso disponibles.

*Este comando no requiere parámetros adicionales.*

##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario envía el comando en el canal de Discord.
 2. El bot difiere la respuesta (`defer()`) para operaciones lentas de base de datos.
 4. El bot responde con un Embed de Discord con los detalles de la operación.

---

#### 🔹 Comando `/inventario`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `inventario()` en línea 99
- **Descripción:** Muestra los artículos que posees.

*Este comando no requiere parámetros adicionales.*

##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario envía el comando en el canal de Discord.
 2. El bot difiere la respuesta (`defer()`) para operaciones lentas de base de datos.
 4. El bot responde con un Embed de Discord con los detalles de la operación.

---

#### 🔹 Comando `/comprar`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `comprar()` en línea 147
- **Descripción:** Compra un artículo de la tienda por su ID.

| Parámetro | Tipo | Descripción | Requerido |
| :--- | :--- | :--- | :--- |
| `articulo_id` | `int` | ID del artículo a comprar | Sí |


##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario envía el comando en el canal de Discord.
 2. El bot difiere la respuesta (`defer()`) para operaciones lentas de base de datos.
 4. El bot responde con un Embed de Discord con los detalles de la operación.

---

#### 🔹 Comando `/usar`

- **Tipo:** Slash Command (Comando de Barra)
- **Método en Código:** `usar()` en línea 192
- **Descripción:** Usa un artículo consumible de tu inventario por su ID.

| Parámetro | Tipo | Descripción | Requerido |
| :--- | :--- | :--- | :--- |
| `articulo_id` | `int` | ID del artículo a usar | Sí |


##### ⚙️ Lógica Interna y Validaciones:
- **Validaciones estándar:** El comando realiza comprobaciones básicas de existencia de usuario en BD.


##### 🎮 Demostración del Flujo de Interacción:
 1. El usuario envía el comando en el canal de Discord.
 2. El bot difiere la respuesta (`defer()`) para operaciones lentas de base de datos.
 4. El bot responde con un Embed de Discord con los detalles de la operación.

---

## 💼 Módulos de Trabajo Interactivos (Mini-juegos de `/trabajo`)

Estos archivos en `src/commands/economy/` no definen comandos slash independientes directos, sino que implementan los mini-juegos interactivos que se inician al presionar los botones del panel `/trabajo`.

### 💼 Trabajo: Artista

- **Archivo de Implementación:** `src/commands/economy/artista.py`
- **Descripción del Trabajo:** Mini-juego de pintura y creación de obras de arte.
- **Funcionamiento y Lógica del Mini-juego:**
  El usuario selecciona colores en una paleta y aplica pinceladas. Se pueden desbloquear combinaciones especiales y estilos de arte (Impresionismo, Cubismo, Realismo) según el nivel. En nivel alto (>=8), se habilita la subasta de la obra con ofertas dinámicas de Mecenas, Coleccionistas u Ofertas Anónimas.

- **Funciones de Base de Datos Involucradas:**
  - `get_balance`
  - `set_balance`
  - `registrar_transaccion`
  - `add_experiencia_trabajo`
  - `get_energia`
  - `set_energia`
  - `usuario_tiene_mejora`

---

### 💼 Trabajo: Cazarrecompensas

- **Archivo de Implementación:** `src/commands/economy/cazarrecompensas.py`
- **Descripción del Trabajo:** Mini-juego de captura de fugitivos.
- **Funcionamiento y Lógica del Mini-juego:**
  Se selecciona un contrato de captura con cierta dificultad. El jugador debe seguir pistas, elegir el equipamiento y combatir o arrestar al fugitivo usando tácticas.

- **Funciones de Base de Datos Involucradas:**
  - `get_balance`
  - `set_balance`
  - `registrar_transaccion`
  - `add_experiencia_trabajo`
  - `get_energia`
  - `set_energia`

---

### 💼 Trabajo: Chef

- **Archivo de Implementación:** `src/commands/economy/chef.py`
- **Descripción del Trabajo:** Mini-juego de preparación de recetas culinarias.
- **Funcionamiento y Lógica del Mini-juego:**
  El bot presenta una receta (ej. hamburguesa, pizza) con ciertos ingredientes sugeridos. El usuario debe agregar los ingredientes correctos en el orden adecuado, controlar los tiempos de cocción y servir. Se califica el plato de 0 a 100.

- **Funciones de Base de Datos Involucradas:**
  - `get_balance`
  - `set_balance`
  - `registrar_transaccion`
  - `add_experiencia_trabajo`
  - `get_energia`
  - `set_energia`

---

### 💼 Trabajo: Científico

- **Archivo de Implementación:** `src/commands/economy/cientifico.py`
- **Descripción del Trabajo:** Mini-juego de experimentos y reacciones químicas.
- **Funcionamiento y Lógica del Mini-juego:**
  El científico mezcla reactivos con diferentes niveles de inestabilidad y afinidad. Debe completar un número de rondas sin superar el 100% de inestabilidad (explosión). Habilidades como 'Estabilizador Térmico' y 'Analizador de Sinergia' ayudan a mitigar riesgos.

- **Funciones de Base de Datos Involucradas:**
  - `get_balance`
  - `set_balance`
  - `registrar_transaccion`
  - `add_experiencia_trabajo`
  - `get_energia`
  - `set_energia`

---

### 💼 Trabajo: Hacker

- **Archivo de Implementación:** `src/commands/economy/hacker.py`
- **Descripción del Trabajo:** Mini-juego de simulación de hackeo de servidores.
- **Funcionamiento y Lógica del Mini-juego:**
  El usuario debe seleccionar IP y puertos vulnerables, descifrar contraseñas o evadir cortafuegos (firewalls) mediante interacción rápida. Mayor nivel permite hackear sistemas más complejos con mejores recompensas.

- **Funciones de Base de Datos Involucradas:**
  - `get_balance`
  - `set_balance`
  - `registrar_transaccion`
  - `add_experiencia_trabajo`
  - `get_energia`
  - `set_energia`

---

### 💼 Trabajo: Ladrón

- **Archivo de Implementación:** `src/commands/economy/ladron.py`
- **Descripción del Trabajo:** Mini-juego de hurtos y sigilo.
- **Funcionamiento y Lógica del Mini-juego:**
  El ladrón planea golpes a tiendas, casas o bancos. Debe evadir cámaras de seguridad, guardias y forzar cerraduras. Fallar el sigilo puede resultar en arresto y multas.

- **Funciones de Base de Datos Involucradas:**
  - `get_balance`
  - `set_balance`
  - `registrar_transaccion`
  - `add_experiencia_trabajo`
  - `get_energia`
  - `set_energia`

---

### 💼 Trabajo: Mecánico

- **Archivo de Implementación:** `src/commands/economy/mecanico.py`
- **Descripción del Trabajo:** Mini-juego de reparación de vehículos.
- **Funcionamiento y Lógica del Mini-juego:**
  El mecánico recibe un diagnóstico de fallo en el motor, frenos, transmisión, etc. Debe elegir las herramientas correctas y los repuestos adecuados para reparar el vehículo de forma segura y eficiente.

- **Funciones de Base de Datos Involucradas:**
  - `get_balance`
  - `set_balance`
  - `registrar_transaccion`
  - `add_experiencia_trabajo`
  - `get_energia`
  - `set_energia`

---

### 💼 Trabajo: Médico

- **Archivo de Implementación:** `src/commands/economy/medico.py`
- **Descripción del Trabajo:** Mini-juego de tratamiento y diagnóstico médico.
- **Funcionamiento y Lógica del Mini-juego:**
  El médico atiende pacientes de urgencia, diagnostica sus síntomas (fiebre, dolor, fracturas) y prescribe tratamientos, medicamentos o cirugía. Curar exitosamente da grandes sumas de dinero.

- **Funciones de Base de Datos Involucradas:**
  - `get_balance`
  - `set_balance`
  - `registrar_transaccion`
  - `add_experiencia_trabajo`
  - `get_energia`
  - `set_energia`

---

### 💼 Trabajo: Minero

- **Archivo de Implementación:** `src/commands/economy/minero.py`
- **Descripción del Trabajo:** Mini-juego de excavación y recolección de minerales.
- **Funcionamiento y Lógica del Mini-juego:**
  El usuario decide qué profundidad excavar (segura, profunda o peligrosa). A mayor profundidad, mayor riesgo de derrumbe o pérdida de energía, pero mayor posibilidad de encontrar gemas o diamantes valiosos.

- **Funciones de Base de Datos Involucradas:**
  - `get_balance`
  - `set_balance`
  - `registrar_transaccion`
  - `add_experiencia_trabajo`
  - `get_energia`
  - `set_energia`

---

### 💼 Trabajo: Pescador

- **Archivo de Implementación:** `src/commands/economy/pescador.py`
- **Descripción del Trabajo:** Mini-juego de pesca con caña y carnada.
- **Funcionamiento y Lógica del Mini-juego:**
  El usuario lanza la caña en diferentes cuerpos de agua (río, lago, mar) y debe reaccionar en el momento justo cuando un pez muerde la carnada. Peces raros y legendarios otorgan más dinero y XP.

- **Funciones de Base de Datos Involucradas:**
  - `get_balance`
  - `set_balance`
  - `registrar_transaccion`
  - `add_experiencia_trabajo`
  - `get_energia`
  - `set_energia`

---

### 💼 Trabajo: Piloto

- **Archivo de Implementación:** `src/commands/economy/piloto.py`
- **Descripción del Trabajo:** Mini-juego de pilotaje de aviones comerciales o de carga.
- **Funcionamiento y Lógica del Mini-juego:**
  El piloto debe gestionar el despegue, mantener el vuelo estable ante turbulencias y realizar un aterrizaje seguro tomando decisiones rápidas. Los errores pueden causar fallos mecánicos y multas.

- **Funciones de Base de Datos Involucradas:**
  - `get_balance`
  - `set_balance`
  - `registrar_transaccion`
  - `add_experiencia_trabajo`
  - `get_energia`
  - `set_energia`

---
