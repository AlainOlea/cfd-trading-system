# Indicadores de Liquidez Macroeconómica y Temporalidad de Inversión

**Última actualización**: 2026-08-10
**Estado**: Activo — documento educativo/navegación, no asesoría financiera
**Skill asociada**: `.claude/skills/macro-liquidity/` (instalada de `star23/Day1Global-Skills`)

---

## Contenido

1. [El marco general: la liquidez como "nivel de agua" del sistema](#1-el-marco-general)
2. [Proveniencia: quién los creó, quién los actualiza y cómo se calculan](#2-proveniencia)
3. [Temporalidad: cómo estos índices explican *cuándo* invertir](#3-temporalidad)
4. [Indicador 1 — Fed Net Liquidity (WALCL − TGA − ON RRP)](#4-indicador-1--fed-net-liquidity)
5. [Indicador 2 — SOFR (Secured Overnight Financing Rate)](#5-indicador-2--sofr)
6. [Indicador 3 — MOVE Index (volatilidad del Tesoro)](#6-indicador-3--move-index)
7. [Indicador 4 — Señales del Yen Carry Trade (USDJPY + spread 2Y)](#7-indicador-4--señales-del-yen-carry-trade)
8. [Síntesis: la matriz de liquidez y el timing práctico](#8-síntesis-la-matriz-de-liquidez)
9. [Limitaciones, advertencias y trampas comunes](#9-limitaciones)
10. [Integración con este sistema CFD](#10-integración-con-este-sistema-cfd)
11. [Fuentes](#11-fuentes)

---

## 1. El marco general

La liquidez macro es, en una frase, **cuánto dinero hay realmente circulando en el sistema financiero listo para financiar posiciones**. Cuando hay abundancia, los precios de los activos tienden a subir; cuando escasea, se comprimen. La fórmula más citada es la del **Fed Net Liquidity**:

```
Net Liquidity = Activos Totales de la Fed (WALCL) − Cuenta General del Tesoro (TGA) − Reverse Repo Nocturno (ON RRP)
```

Pero el sistema de la skill `macro-liquidity` no se queda ahí: monitorea **4 indicadores que forman una cadena completa**, del "grifo principal" de la Fed hasta el "final del tubo" en el mercado:

| # | Indicador | Qué responde | Nivel de "tubería" |
|---|-----------|--------------|--------------------|
| 1 | Fed Net Liquidity | ¿La Fed inyecta o drena efectivamente? | El **grifo principal** (cantidad) |
| 2 | SOFR | ¿Falta cash en el fondeo nocturno? | La **presión del tubo** (estrés agudo) |
| 3 | MOVE Index | ¿El mercado de bonos, ancla de precios, está tranquilo o nervioso? | El **voltímetro** de la incertidumbre |
| 4 | Yen Carry Trade | ¿El apalancamiento oculto del mundo está a punto de deshacerse? | La **bomba de tiempo** (apalancamiento) |

La idea operativa: ningún indicador tiene sentido aislado. **El timing de inversión sale de leerlos en conjunto y en su frecuencia temporal correcta.** Ese es el tema central de este documento.

---

## 2. Proveniencia

Cada indicador tiene un origen distinto: algunos son **índices oficiales** administrados por instituciones (SOFR), otros son **índices privados** construidos por bancos de inversión (MOVE), otros son **fórmulas analíticas** popularizadas por analistas sobre datos públicos (Net Liquidity), y uno es una **estrategia de mercado** sin creador (el yen carry). Resumen:

| Indicador | Creador | Mantenedor actual | Frecuencia | Cálculo en una línea |
|-----------|---------|-------------------|------------|----------------------|
| Fed Net Liquidity | Fórmula popularizada por **Max Anderson** (~2020); los datos los produce la **Fed** | FRED/Fed H.4.1 (datos); terceros la recomputan (DollarLiquidity.com, Eco3min) | Semanal (H.4.1, jueves 16:30 ET) | `WALCL − TGA (WTREGEN) − ON RRP (RRPONTSYD)`, en $MM |
| SOFR | **ARRC** (comité Fed Board + NY Fed), elegido en 2017; reemplazó a LIBOR en 2023 | **Federal Reserve Bank of New York** | Diaria (~08:00 ET, datos del día previo) | Mediana ponderada por volumen de 3 segmentos de repo del Tesoro |
| MOVE | **Harley Bassman**, Merrill Lynch, 1994 | **ICE Data Indices / ICE BofA** | Diaria (opciones de 1 mes) | `0.20σ₂Y + 0.20σ₅Y + 0.40σ₁₀Y + 0.20σ₃₀Y` (vol implícita ATM) |
| Yen carry | Nadie: es una **estrategia de mercado**, no un índice | — (datos: BOJ, MOF de Japón, Treasury de EE.UU.; análisis del **BIS**) | Continua | Basado en `USDJPY` y `US2Y − JP2Y` |

### 2.1 Fed Net Liquidity — creador y mantenimiento

- **La fórmula** fue popularizada por **Max Anderson** (estratega macro), quien en 2020 propuso que el desglose `Balance de la Fed − TGA − Reverse Repo` era la forma correcta de medir la liquidez efectiva (antes, el balance solo bastaba porque TGA/RRP eran insignificantes). Anderson reportó correlaciones de 0.85–0.95 con el S&P 500 en su ventana de origen y una transmisión de ~2 semanas.
- **Los datos los produce la Reserva Federal** (no Anderson): la serie semanal **H.4.1** ("Factors Affecting Reserve Balances"), publicada cada jueves a las 16:30 ET con referencia del miércoles previo. En FRED se sirven como `WALCL` (activos totales), `WTREGEN` (TGA) y `RRPONTSYD` (ON RRP).
- **Quién la actualiza hoy**: la propia Fed (el dato oficial). Terceros la **recomputan** sobre esos datos: DollarLiquidity.com (API gratuita, refresco cada 6 h), Eco3min (datasets históricos alineados), Kunkel Capital, etc. La skill `macro-liquidity` la calcula en vivo con `web_search` sobre FRED/NY Fed/Treasury.
- **Cálculo**: `Net Liquidity = WALCL − TGA − ON RRP`, todo en millones de dólares, semanal.

### 2.2 SOFR — creador y mantenimiento

- **Creador**: el **Alternative Reference Rates Committee (ARRC)**, comité público-privado convocado por la Junta de la Reserva Federal y la Fed de Nueva York, que en **2017** seleccionó a SOFR como sustituto preferido del USD LIBOR (tras el escándalo de manipulación de LIBOR y la pérdida de transacciones subyacentes). La transición se completó en 2023.
- **Mantenedor**: el **Federal Reserve Bank of New York**, que lo publica cada día hábil ~08:00 ET (los datos son de las transacciones del día hábil previo). Se puede corregir hasta las 14:30 ET; por eso los usuarios institucionales lo referencian tras esa hora.
- **Cálculo**: **mediana ponderada por volumen** de transacciones en tres segmentos del mercado de repo del Tesoro:
  1. **Tri-party repo** (plataforma de BNY Mellon + datos del OFR).
  2. **GCF repo** (repo entre dealers).
  3. **Repo bilateral** compensado por el servicio **DVP de FICC** (con filtro de "specials").
  Volumen subyacente: ~**$1T diario**. Cumple principios **IOSCO**; es 100% transaccional (imposible de manipular), a diferencia de LIBOR.
- Series FRED: `SOFR` (spot), `SOFR30DAYAVG` / `SOFR90DAYAVG` (promedios), `DFEDTARU` (techo del rango fed funds), `IORB`.

### 2.3 MOVE — creador y mantenimiento

- **Creador**: **Harley Bassman** (el "Convexity Maven"), en **Merrill Lynch, 1994**, para dar a las mesas de rates un solo número legible de riesgo forward de rendimientos del Tesoro. Innovación metodológica clave: opciones de **expiración constante de 1 mes** y **volatilidad normalizada** (en bp de yield, no % de precio), que evita los problemas de las opciones sobre futuros (cheapest-to-deliver, cupones distintos).
- **Mantenedor**: tras la compra de Merrill por Bank of America y la adquisición de los índices de BofA Merrill por ICE, el índice hoy es **ICE BofA MOVE**, administrado por **ICE Data Indices**. Se publica con datos de **Bloomberg** (`MOVE Index`) y está disponible casi en tiempo real ("near intra-day pricing").
- **Cálculo**: promedio ponderado de la **volatilidad implícita at-the-money de opciones de 1 mes** sobre los puntos 2Y, 5Y, 10Y y 30Y de la curva del Tesoro, con pesos **20% / 20% / 40% / 20%** (el 10Y lleva el mayor peso porque es el ancla global de duration). Se expresa en **puntos base de volatilidad de rendimiento anualizada**.
- Interpretación: un MOVE de 100 = el mercado cotiza ±100bp de rango anualizado en los yields (≈ ±6.3bp diarios; 100 ÷ 15.9).

### 2.4 Yen carry — sin creador

- El yen carry **no tiene creador ni mantenedor**: no es un índice oficial, es una **estrategia de inversión** (pedir prestado yen barato e invertir en activos de mayor yield) que existe desde hace décadas. Su "proveniencia" es el propio diferencial de tasas EE.UU.–Japón.
- **Los datos** provienen de fuentes públicas: `USDJPY` (mercado FX, Yahoo `JPY=X`/`USDJPY`), yields US 2Y (Treasury de EE.UU., FRED `DGS2`) y JGB 2Y (Banco de Japón / MOF de Japón). La política del BoJ (hikes, YCC) es el driver.
- **Quién lo estudia**: el **BIS** publica análisis periódicos sobre el tamaño y los riesgos del carry (p. ej. Bulletin 90, agosto 2024); Goldman Sachs y Reuters mantienen explainers. El tamaño se estima en ~**$250–500B** dependiendo de la definición (BIS: ~¥40T / $250B en la foto de agosto 2024, sesgo a la baja).

---

## 3. Temporalidad

### 2.1 Definición operativa

"Temporalidad" aquí significa: **en qué horizonte de tiempo cada serie es informativa y por qué su señal aparece antes o después que el precio de los activos**. Hay una jerarquía de frecuencias que conviene internalizar:

| Escala | Serie | Frecuencia de publicación | Horizonte útil |
|--------|-------|---------------------------|----------------|
| Días | SOFR, USDJPY | Diaria (SOFR 08:00 ET) | Días a semanas |
| Semanas | Net Liquidity, MOVE | Semanal (H.4.1 jueves 16:30 ET); MOVE diario pero señal semanal | Semanas a meses |
| Meses a trimestres | Tendencias de Net Liquidity, ciclo del carry | Mensual/trimestral | 1 a 4 trimestres |
| Años | Acumulación del carry, ciclos QE/QT | Estructural | Ciclo completo |

### 2.2 Los cuatro roles temporales

- **Coincidente**: la Net Liquidity **describe el régimen actual**, no lo predice. Kunkel Capital lo resume: *"es un indicador de régimen coincidente, no leading — cuando la Net Liquidity se da la vuelta, el precio muchas veces ya giró"*. Se usa para decidir **cuánto** estar en riesgo, no cuándo entrar al tick exacto.
- **Adelantado (leading)**: el MOVE **anticipa el VIX** en 5–20 sesiones al inicio de episodios de estrés (Treasuries son la superficie de vol risk-free que precia todo lo demás). Max Anderson (creador del indicador) argumentaba además que la Net Liquidity transmite al mercado en **~2 semanas**, con correlación reportada de ~0.85–0.95 en su ventana de origen.
- **Estrés agudo**: el SOFR es el **termómetro intradía/semanal** de si el fondeo se está secando. Un spike de SOFR suele preceder crisis de financiamiento (caso septiembre 2019), pero revierte rápido.
- **Cola larga / riesgo extremo**: el yen carry es la señal de **acumulación lenta (años) y deshielo violento (días)**. Es leading para eventos de *unwind* global.

### 2.3 Por qué funciona (mecánica del precio)

La liquidez afecta a los precios por tres canales clásicos:

1. **Canal de descuento (discount rate)**: más liquidez → tasas reales más bajas → los múltiplos de activos de larga duración (tech, BTC, oro) se expanden.
2. **Canal de márgenes (financiamiento)**: más reservas → dealers y fondos pueden cargar más balance → más compras con apalancamiento.
3. **Canal de colateral/preferencia de activos**: cuando el MOVE sube, los Treasuries dejan de funcionar como "refugio" y los dealers se contraen → venta mecánica de todo lo que tenga duration.

El punto temporal clave: **el canal de descuento y de márgenes actúan con rezago (semanas–trimestres)**; el canal de estrés (SOFR, MOVE) es **casi inmediato**. Por eso un cuadro "ample" de liquidez macro no te dice nada sobre lo que pasará esta semana, pero sí sobre la dirección estructural del siguiente trimestre; y un MOVE >130 sí te dice que esta semana debes respetar los stops más de cerca.

### 2.4 Advertencia central

La correlación Net Liquidity↔S&P 500 **no es estable entre regímenes**. Eco3min midió 0.81 en 2020–2022 y ≈ −0.03 en 2023–2024 (mientras el S&P subía >40%). El veredicto académico/institucional: la Net Liquidity es un **diagnóstico de plomería** (cuándo la postura titular de la Fed diverge de la liquidez efectiva), no un **market-timing indicator**. Se usa como **filtro de régimen para el tamaño de posición**, no como señal de entrada/salida mecánica.

---

## 4. Indicador 1 — Fed Net Liquidity

### 3.1 Definición y desglose

```
Net Liquidity = WALCL − TGA (WTREGEN) − ON RRP (RRPONTSYD)
```

- **WALCL** (Fed Total Assets): todo lo que la Fed tiene en cartera (Treasuries + MBS). Cuando la Fed hace QE (compra bonos), los activos suben y *imprime* dinero que inyecta en la economía. Cuando hace **QT** (dejar vencer sin reinvertir), los activos caen y *drena* dinero. Es el **tamaño del estanque**.

  Analogía del estanque, el embalse y el estacionamiento (tomada de la skill):
  - WALCL = tamaño total del estanque de agua.
  - **TGA** = el embalse del gobierno: el "chequera" del Tesoro en la Fed. Cuando el Tesoro emite deuda y el efectivo entra a la TGA, ese dinero sale del sistema bancario privado (**drena**). Cuando el Tesoro gasta, el dinero vuelve al mercado (**inyecta**). Reconstrucción agresiva de TGA tras una crisis de techo de deuda = drenaje rápido.
  - **ON RRP** = el estacionamiento de la Fed: los money market funds "parkean" cash ahí a una tasa fija que fija la Fed. Dinero en el RRP **no circula**. Cuando el balance del RRP cae, ese dinero sale del estacionamiento y va a T-bills, repo o activos de riesgo (**inyecta**).

### 3.2 El gran caso de estudio: por qué el QT no dolió (2022–2026)

El hallazgo más importante del período: entre septiembre 2022 y marzo 2026, el **ON RRP drenó $2.37T** hacia el sistema mientras la Fed retiraba **$2.14T** vía QT. El drenaje del RRP **superó al QT en ~$230B** (offset de ~110%). Resultado: la liquidez efectiva no cayó, y el S&P 500 subió 78% (de 3,719 a 6,625) durante la "contracción más agresiva de la historia moderna". Analistas que miraban solo WALCL esperaban un replay del taper tantrum 2018; la plomería (TGA/RRP) compensó al titular.

Fechas clave de la historia:
- WALCL pico: **abril 2022** ($8.97T). Net Liquidity pico: **septiembre 2021** ($7.14T) — **antes** del pico del balance, porque el ON RRP empezó a absorber reservas.
- El mercado hizo pico en **enero 2022**, alineándose más con el pico de Net Liquidity que con el de WALCL.
- ON RRP pico: 28-sep-2022 ($2.37T), justo cuando el S&P 500 estaba cerca de su mínimo de 2022 (3,719).
- **"Stealth Easing"**: mayo 2023 – diciembre 2025 (63 semanas): WALCL cayendo pero Net Liquidity expandiéndose; S&P +64.6%.

### 3.3 Evidencia de correlación (números duros)

| Período | Net Liq ↔ S&P | WALCL ↔ S&P | Observaciones |
|---------|---------------|-------------|---------------|
| Full sample 2016–2026 | 0.73 | 0.60 | Mejora consistente con el desglose de 3 componentes |
| COVID 2020–2022 | 0.81 | 0.74 | Liquidez era la fuerza dominante |
| QT era 2022–2026 | −0.38 | −0.95 | La plomería explica la divergencia |
| 2023–2024 | −0.03 | −0.96 | El rally lo dominaron earnings de IA, no liquidez |

Rolling correlation 52-semanas: pico 0.94 (mediados 2021), −0.57 (mediados 2025), ~−0.80 (marzo 2026). **La relación es dependiente del régimen.**

### 3.4 Temporalidad y reglas prácticas

- **Frecuencia**: semanal (H.4.1, publicado cada jueves 16:30 ET, referencia del miércoles previo).
- **Transmisión**: ~2 semanas según Anderson ("un cambio de liquidez se propaga al precio en ~2 semanas"), aunque la visión dominante actual es que es **coincidente y de régimen**.
- **Horizonte útil**: 1 a 4 trimestres. No sirve para el intraday.
- **Regla del umbral**: mover de 8 semanas normalizado; fuera de ±1.5% del nivel promedio = señal de régimen. Un bump de $50B semanal es ruido; $200B en 4 semanas es régimen.
- **Noise estacional**: mediados de abril (impuestos) jala cientos de miles de millones a la TGA en una semana — parece drenaje pero es mecánico, y revierte. Junio, septiembre, diciembre tienen bumps menores. Ajustar estacionalidad o lag 2 semanas.
- **Qué hacer en cada régimen** (Kunkel):
  - **Régimen de liquidez al alza**: los dips se compran, los breakouts se sostienen, los shorts de duration larga se atropellan.
  - **Régimen a la baja**: los rallies se desvanecen, el soporte falla en el segundo test, se premia calidad aburrida.
  - No es un pronóstico: es una **decisión de tamaño de posición** ("¿estoy posicionado para el régimen donde estoy?").

### 3.5 Limits específicos

- Es una medida **US-only**. La liquidez global incluye PBoC, BoJ, ECB; cuando la US está plana pero el credit impulse chino acelera, los activos de riesgo pueden subir sin ayuda de la Fed (fase 2024).
- Mide **cantidad**, no **precio del dinero**. Un régimen ajustado con tasas reales cayendo puede ser positivo; uno holgado con tasas reales subiendo puede doler. Se necesitan los dos ejes.
- Cuando importa más el **colateral** que la cantidad de reservas (blowups de repo, basis trade, sep-2019), la plomería se congela y el índice se ve bien la semana siguiente — pero las posiciones ya se liquidaron.

---

## 5. Indicador 2 — SOFR

### 4.1 Definición

SOFR = **Secured Overnight Financing Rate**. Es el costo de pedir cash prestado *de un día para otro* contra colateral de Treasuries en el mercado de **repos**. Es una medida de repo genérico (sin las "specials") calculada por la Fed de Nueva York.

Un repo es, en esencia, como una hipoteca: pides cash hoy y entregas un Treasury como garantía; al día siguiente devuelves el cash con intereses y recuperas el colateral. En el mercado de repos:

- El **prestamista** (cash) gana interés con riesgo casi nulo (colateral del gobierno).
- El **prestatario** (quien necesita cash, normalmente bancos/dealers/hedge funds) consigue fondeo de corto plazo.

### 4.2 Cómo se calcula

Es la **mediana ponderada por volumen** de transacciones en tres segmentos del mercado de repo del Tesoro:

1. **Tri-party repo** (Banco de Nueva York Mellon + OFR).
2. **GCF repo** (transacciones entre dealers).
3. **Repo bilateral** compensado por el servicio DVP de FICC.

Detrás hay ~**$1 trillón de transacciones diarias**, con participación diversa (asset managers, bancos, broker-dealers, aseguradoras, money market funds, pensiones, lenders de valores). Es por eso que reemplazó a LIBOR (que dependía de ~$1B diario y opiniones de panel de bancos): SOFR es **100% transaccional, imposible de manipular**, publicado por la Fed de Nueva York conforme a principios IOSCO. De aquí que trillones de dólares en derivados, hipotecas y préstamos flotantes ahora se coticen contra SOFR.

### 4.3 Cómo leerlo contra el resto del mundo de tasas

| Tasa | Qué es | Nota |
|------|--------|------|
| Fed Funds target | Rango objetivo de la Fed (ej. 3.50–3.75%) | Fija el piso del sistema |
| EFFR | Tasa **no asegurada** interbancaria efectiva | Muy estable; la Fed la controla bien |
| **SOFR** | Tasa **asegurada** (con colateral de Treasuries) | Más volátil, transaccional |
| IORB | Tasa que la Fed paga por reservas (3.65%) | Fija el piso de muchas tasas |

**Señal clave: el spread SOFR vs. tasa administrada (IORB/fed funds).** Un SOFR muy por encima del piso indica **escasez aguda de cash nocturno**. La skill usa: SOFR > techo del rango fed funds + 10bp → 🔴 estrés extremo. El CME lo formula como SOFR−EFFR: un SOFR muy por encima del EFFR = poco cash.

### 4.4 Casos históricos

- **Septiembre 2019 (la "crisis del repo")**: SOFR saltó de ~2% a más de 5% en una noche; la Fed tuvo que inyectar liquidez de emergencia y creó el repo facility permanente.
- **Finales de trimestre / año**: SOFR sube de forma sistemática en quarter-ends (window dressing bancario por ratios regulatorios). +25bp en algunos quarter-ends de 2023. Estacional, no disruptivo — pero **el tamaño del salto es un medidor de tightness** mientras se normaliza el balance.
- **15-sep-2025**: SOFR 4.51% vs EFFR 4.33% (+18bp) por impuestos corporativos y settlements; bancos usaron el **Standing Repo Facility (SRF)** ($1.5B). Temporal, revirtió al día siguiente — pero mostró cómo un drenaje de cash puntual presiona el fondeo.
- **Fluctuación “normal”**: SOFR se mantiene típicamente dentro del rango del fed funds y por encima del IORB. Movimientos diarios pequeños son ruido.

### 4.5 Temporalidad y uso

- **Frecuencia**: diaria (publicado ~08:00 ET para las transacciones del día previo).
- **Horizonte**: días a semanas. Es el indicador de **estrés agudo**; no de tendencia.
- **Cómo usarlo para timing**:
  - Un **spike súbito** (SOFR rompiendo el techo +10bp, uso del SRF) es una **señal de alerta inmediata**: cubrir, reducir riesgo de corto plazo, ya que suele ser precursor de crisis de fondeo.
  - Pero **no sobreactúes a spikes estacionales** (quarter-ends, impuestos): revierten en 1–2 días.
  - Para el horizonte medio, lo útil es el **promedio compuesto** de SOFR (los contratos se referencian a promedios de 30/90 días), que suaviza el ruido diario.
- **Derivados**: los futuros de SOFR (CME) permiten cotizar expectativas forward del nivel de tipos — hoy casi 2M contratos de SOFR 1M — una forma de leer qué espera el mercado sobre la política de la Fed, adelantado al dato real.

**Nota sobre el IORB y el balance normalizado**: conforme la Fed sigue recortando balance, los quarter-end moves del SOFR crecen en magnitud y se vuelven un **medidor de que las reservas se vuelven menos abundantes**. Es uno de los indicadores a vigilar en la transición 2026.

---

## 6. Indicador 3 — MOVE Index

### 5.1 Definición

El **MOVE** (Merrill Lynch Option Volatility Estimate, hoy *ICE BofA MOVE*) es el **VIX de los bonos**. Fue construido por Harley Bassman en Merrill Lynch en 1994 para dar a las mesas de rates un solo número legible de riesgo forward de rendimientos. Es un promedio ponderado de la **volatilidad implícita de opciones at-the-money de un mes** sobre cuatro puntos de la curva del Tesoro de EE.UU.:

```
MOVE = 0.20·σ(2Y) + 0.20·σ(5Y) + 0.40·σ(10Y) + 0.20·σ(30Y)
```

Se expresa en **puntos base de volatilidad de rendimiento anualizada** (no porcentaje de precio como el VIX). La ponderación de 40% en el 10Y no es casual: el 10Y es el **ancla global de la tasa de descuento** y el punto de la curva con mayor liquidez de opciones.

### 5.2 Qué significa un número concreto

Un MOVE de 100 significa que el mercado de opciones cotiza **±100bp de rango anualizado** en los rendimientos del Tesoro (≈ ±6.3bp diarios, porque 100/15.9 ≈ 6.3). En términos probabilísticos (regla de Bassman/vix): si el 10Y está en 4.10% y MOVE=100, hay ~68% (1 sigma) de probabilidad de que en un año cierre entre 3.10% y 5.10%.

### 5.3 Bandas y régimen

| MOVE | Régimen | Consecuencia |
|------|---------|--------------|
| < 80 | Calma / complacencia | Operan a pleno riesgo los carry, risk-parity y vol-targeting. Ojo: niveles ultrabajos suelen ser preludios de explosión (LTCM 1998: <70 → record 198). |
| 80–120 | Normal | Los fondos macro posicionan con convicción; el dólar cotiza por diferenciales no por seguridad; las acciones respetan su media de 50 días. |
| 130+ | **Estrés** | **Los Treasuries dejan de ser refugio y se vuelven activo de riesgo**: el basis trade se deshace, los dealers se contraen, el dólar recibe bid de haven, y los vol-targeting venden forzosamente. Umbral de la skill: 🔴. |
| 150+ | Crisis | 2020 llegó a 163, 2023 regional banks >180–199. Aquí la Fed se ve forzada a intervenir. Dejas de operar el macro y operas la función de reacción de política. |

Extremos históricos: **264** (oct 2008, Lehman), **217** (6-oct-2008, el récord "post-LTCM"), **246** proxy en 1987 (Black Monday), **199** (marzo 2023, SVB/Credit Suisse), **164** (marzo 2020), >**140** durante semanas (oct 2023, 30Y >5%). El ciclo 2022 promedió ~130 vs. promedio de 55 en 2017–2019.

### 5.4 Mecanismo de transmisión y por qué "adelanta" al VIX

En episodios de estrés macro, **el MOVE se mueve primero que el VIX** (5–20 sesiones de adelanto). Los casos documentados: feb 2018 (XIV blowup), Q4 2018 (policy error), marzo 2020 (MOVE hizo máximos días antes de que el VIX llegara a 80), crisis gilt del Reino Unido 2022, y marzo 2023 (la divergencia MOVE–VIX telegrafió el estrés regional antes de que el equity lo entendiera).

**¿Por qué?** Los Treasuries son la **superficie de volatilidad risk-free contra la que se precia todo lo demás**. Cuando el vol del bono sube, el costo de cobertura de los dealers sube, el balance de los dealers se contrae, y el bid-ask del long end se ensancha. Eso se propaga: spreads de crédito más anchos, vol de equity que sube con rezago, vol de FX que sube. Las valoraciones de equity son función de la tasa de descuento, que es función de las expectativas de rendimientos → si el descuento fluctúa, las acciones no pueden quedarse quietas.

**Ratio MOVE/VIX**: la banda normal de largo plazo es ~5–7 (MOVE ~100, VIX ~15–18). Si el ratio corre **por encima** de la banda, el mercado de bonos está preciando más estrés que el de acciones: es la **impresión de alerta temprana**. Si corre por debajo, el vol de equity grita más que el de bonos → típicamente riesgo idiosincrático, no sistémico.

La interacción más peligrosa: **picos de MOVE y VIX simultáneos** = desapalancamiento amplio (deleveraging). Eso es exactamente lo que ocurrió en el unwind del carry de agosto 2024 (ver indicador 4).

### 5.5 Temporalidad y uso

- **Frecuencia**: diario (nótese: el índice mismo refleja opciones de **un mes**, así que su horizonte de señal es ~mensual, incluso si se publica cada día).
- **Rol**: leading de estrés cross-asset (adelanta al VIX), y medidor de **evento**: FOMC, subastas (tails de aducción corren casi perfectamente con el MOVE al día siguiente), elecciones, NFP.
- **Uso práctico para timing**:
  - MOVE >130 + VIX subiendo = **despacito**: reducir tamaño, respetar stops.
  - Ratio MOVE/VIX > banda = el bonos sabe algo que las acciones no: momento de revisar coberturas.
  - MOVE <80 = apalancamiento cómodo, pero atención a la complacencia (vol de vol): los burst de vol tienden a salir precisamente de pisos de MOVE.
  - En piso de MOVE + carry trade del yen maximizado = la tormenta perfecta (BIS describe este patrón procyclical).

---

## 7. Indicador 4 — Señales del Yen Carry Trade

### 6.1 Qué es el carry trade

El **yen carry** es la estrategia de apalancamiento más grande del mundo. Mecánica:

1. El Banco de Japón mantiene (o mantuvo durante décadas) tasas cerca de 0% → pedir prestado yen es casi gratis.
2. Conviertes ese yen a dólares (o pesos, etc.) → el yen se deprecia, USDJPY sube.
3. Invistes los dólares en activos de mayor rendimiento: Treasuries, acciones de EE.UU., gestión de treasury, mercados emergentes.
4. La ganancia = el **diferencial de tasas** (tasa EE.UU. − tasa Japón). Mientras dure el diferencial y el vol no explote, cosecha "monedas de a diez centavos frente a una apisonadora" (la metáfora clásica de los carry).

Se implementa con forwards, FX swaps, opciones (on y off balance sheet), y también préstamos interbancarios de yen a entidades fuera de Japón. El **BIS** estima el tamaño en ~**¥40T (~$250B)** en la foto de agosto 2024 (bola media, sesgada a la baja), con rangos de hasta $500B+ según la definición (claims de yen bancarios cross-border sobre SPVs). Solo en futuros netos short de yen, los especuladores tenían ~¥2T (~$14B), récord histórico.

### 6.2 Por qué importa para tus activos

Porque el carry es **apalancamiento oculto dentro de todos los mercados**: cuando se deshace, los traders venden lo que sea para cubrir margen → acciones, bonos, cripto, EM. Y el disparador casi siempre es **un spike de volatilidad** (ver MOVE/VIX). Es la interacción "sonrisa del dólar" y "deleveraging procyclical" que el BIS describe.

### 6.3 Las variables de monitoreo

- **USDJPY**: la tasa de cambio directa. USDJPY subiendo = carry activo; yen disparándose (USDJPY cayendo) = unwind en curso.
- **US2Y − JP2Y (spread de 2 años)**: la "fuente de ganancia" del carry. Spread amplio = carry rentable = perennidad; spread estrechándose = la base se erosiona.
  - Ojo con el matiz histórico de la skill: el spread puede ampliarse *mientras* el yen también se debilita porque el carry se acumula — la señal de alerta es la **inversión del movimiento** (yen fuerte + spread cerrando).
- **Política del BoJ**: hikes del BoJ o ajustes al YCC son el fuego. En 2024, el BoJ sorprendió con hike.
- **Intervención (Treasury/BoJ)**: cuando la debilidad del yen llega a extremos, hay intervención coordinada (último caso, agosto 2026, primera intervención conjunta EE.UU.–Japón en 15 años).

### 6.4 Casos históricos

- **Julio–agosto 2024**: el BoJ subió tasas en una semana en que el dato de empleo de EE.UU. decepcionó. El yen pasó de debilitarse a apreciarse violentamente; el **Nikkei 225 cayó 12% en un día** (TOPIX −12% el 5-agosto), el VIX tocó niveles vistos solo en COVID, y acciones/cripto a escala global cayeron en cadena. El BIS documenta el episodio: la espiral fue amplificada por **márgenes en aumento** y deleveraging; el mercado se estabilizó rápido, pero solo "en parte" del carry se deshizo.
- **Agosto 2026 (actualidad del momento de escribir esto)**: el yen tocó **163.99/dólar**, mínimo de 40 años; EE.UU. y Japón intervinieron de forma coordinada (primera vez con participación estadounidense en 15 años, vía Exchange Stabilization Fund; se especuló con el FIMA Repo Facility para evitar ventas de Treasuries). El dólar cayó de ~164 a ~155 en días. Al 10-ago-2026, USDJPY ~159 con el spread 2Y en ~2.64%, habiendo hecho techo en ~2.82%.

Warning importante de ING (2026): la intervención no cambia fundamentales — "no empujará USDJPY sosteniblemente por debajo de 155", pero sirve como contención mientras Tokio prepara medidas pro-yen. El carry trade "nunca muere del todo"; se reconstruye.

### 6.5 Temporalidad y uso

- **Acumulación**: meses a años. El carry crece en periodos de vol baja y diferencial de tasas amplio.
- **Deshielo**: **días**. Cuando el vol estalla (MOVE/VIX), el desapalancamiento es mecánico y violento.
- **Criterios de alerta de la skill**:
  - USDJPY cae >3% en una semana (yen fuerte) → 🔴 riesgo de unwind global.
  - Spread 2Y US–JP se estrecha >50bp en un mes → 🔴 la base del carry se erosiona.
  - USDJPY debilitándose + spread cerrándose → 🟡 watch.
  - USDJPY estable/fuerte + spread sostenido → ✅ normal.
- **Cómo usarlo para timing**: es tu **señal de cola** (tail risk). No te dice cuándo comprar BTC; te dice cuándo un evento global de riesgo está en el aire: si el yen dispara más de 3% en una semana junto con MOVE>130, recorta riesgo agresivo — los períodos así revelan cuán correlacionado está todo (todo cae junto).

---

## 8. Síntesis: la matriz de liquidez

### 7.1 La cadena temporal completa

```
   CANAL CANTIDAD                CANAL PRECIO                CANAL APALANCAMIENTO
  Fed Net Liquidity            MOVE/vol de bonos                 Yen carry
   (semanas–trimestres)         (semanas, leading al VIX)        (meses–años de build,
        ↓                                 ↓                     días de unwind)
       SOFR                                                          ↓
   (días, estrés agudo)                                            VIX
```

La **matriz** de la skill combina los 4: cuenta cuántos están en 🔴 y traduce el conteo a un rating:

| Alertas | Rating | Recomendación |
|---------|--------|---------------|
| 0 | 🟢 Ample | Entorno amigable, mantener exposición a riesgo |
| 1 | 🟡 Slightly Tight | Vigilar, revisar stops, moderar apalancamiento |
| 2 | 🟠 Tight | Reducir exposición 10–20%, aumentar cash |
| 3 | 🔴 Dangerous | Reducir fuerte riesgo, giro defensivo (cash, T-bills cortos) |
| 4 | 🔴🔴 Crisis | Minimizar riesgo, cubrir colas |

### 7.2 Tabla de timing por horizonte

| Horizonte | Indicador a mirar | Señal | Acción |
|-----------|-------------------|-------|--------|
| Días | SOFR, VIX, USDJPY | Spike de SOFR, VIX >30, yen fuerte | Reducir/gestionar posiciones de corto plazo |
| Semanas | MOVE, ratio MOVE/VIX | MOVE >130, ratio >7 | Respetar stops, recortar tamaño, cubrir |
| Meses | Tendencias de Net Liquidity (8-sem), spread 2Y | Pendiente ±1.5%, spread cerrando | Ajustar peso de assets de duration larga vs. corta |
| Trimestres | Régimen Net Liquidity, ciclo QE/QT, TGA/RRP | Contraction vs. Stealth Easing | Decidir el **nivel base** de exposición al riesgo |

### 7.3 Ejemplo tridimensional de lectura (snapshot 10-ago-2026)

- **Net Liquidity**: $5.84T, subiendo WoW (~+1.3%), RRP drenado a ~$1.4B → régimen de liquidez **holgada** para las próximas semanas/meses, con matiz: WALCL y Net Liquidity están en **régimen de contracción** interanual (−5.3% Y/Y) → el colchón del RRP está **agotado**; cualquier QT adicional ahora sí drena directo.
- **SOFR**: 3.62%, dentro del rango (3.50–3.75%) → fondeo **normal**.
- **MOVE**: ~72 → banda de calma/complacencia → apalancamiento cómodo, pero ojo: pisos de MOVE preceden bursts de vol.
- **Yen carry**: 🟡 — intervención coordinada reciente, USDJPY 159, spread en 2.64% cerrando desde máximos → riesgo de cola **latente**, no activo.

Lectura de la matriz: **0 alertas activas (🟢 Ample)** con **colas de riesgo vedando** (MOVE bajo + carry acumulado + contracción estructural de net liquidity). Es exactamente el perfil de régimen donde las señales del pipeline long funcionan, pero conviene que el tamaño de posición respete que el *colchón* de liquidez ya no está para absorber un evento.

---

## 9. Limitaciones

1. **La correlación Net Liquidity↔mercado es dependiente del régimen** — funciona en regímenes dominados por liquidez, colapsa en regímenes dominados por earnings (2023–24).
2. **No es un market-timing indicator**: es un *diagnóstico de plomería* y un *filtro de régimen*. No se opera mecánicamente contra la cifra.
3. **No predice turning points**: cuando la liquidez se da la vuelta, el precio muchas veces ya giró (coincidente, no leading para niveles).
4. **Noise estacional** de la TGA/RRP (impuestos de abril/jun/sep/dic, quarter-ends) que hay que ajustar.
5. **US-centrismo**: la liquidez global (ECB, BoJ, PBoC, credit impulse chino) puede dominar fases sin ayuda de la Fed.
6. **Mide cantidad, no precio**: hace falta el eje de tasas reales. Un régimen con tasas reales subiendo + vol de bonos alto puede doler incluso con liquidez nominal holgada.
7. **Datos con lag de 1–2 días** (Net Liquidity semanal publicada jueves para el miércoles previo).
8. **Solo para horizontes medios**: es poco informativo intradía; es un filtro de fondo, no un trigger.

---

## 10. Integración con este sistema CFD

Este proyecto (`cfd-trading-system`) opera señales técnicas + ML sobre 22 tickers (SPY, QQQ, IWM, DIA, GLD, SLV, USO, UNG, AAPL, NVDA, MSFT, AMZN, GOOGL, META, TSLA, BTC-USD, ETH-USD, SOL-USD, XRP-USD, CORN, CPER, DBA) con ejecución paper en Alpaca. La liquidez macro como **overlay de régimen** encaja en los siguientes puntos (ninguna implementación existe aún — este documento es solo el fundamento):

- **Filtro previo al `paper-trade`**: si la matriz marca 🟠/🔴 (2+ alertas), reducir el tamaño de posición del día (el binding cap real es `MAX_POSITION_PCT=5%`) o bajar la frecuencia de operación.
- **Sesgados por duration larga**: GLD, BTC-USD, ETH-USD y las tech (NVDA, TSLA, META) son los más sensibles al canal de descuento → Net Liquidity/MOVE importan más ahí. Los commodities (CORN, CPER, DBA) y USO responden más a oferta/demanda y al dólar que a la liquidez US en aislamiento (Kunkel: "lo que no I the economice… la net liquidity no maneja limpio commodities").
- **Sincronía de crisis**: en un episodio de unwind (MOVE>130 + yen fuerte), la correlación dentro del portfolio se dispara a 1: las 10 posiciones máximas simultáneas pueden perder juntas. La matriz es una alerta de *de-correlation regimense*.
- **Frecuencias**: el pipeline opera 1m/1h/1d. La liquidez macro solo debe leerse en la corrida **diaria** (07:00 ET) — alimenta la decisión de tamaño del día, no el trigger intradía.

Datos de referencia live para reconstruir el indicador en código:
- `WALCL`, `WTREGEN`, `RRPONTSYD`, `SOFR`, `DFEDTARU` (FRED).
- `^MOVE` (Yahoo/TradingView), `USDJPY=X` (Yahoo), `^TYX`~ yields US 2Y/10Y (~/30Y), JGB 2Y (Inversión/TradingView).

---

## 11. Fuentes

- Skill `macro-liquidity` — `star23/Day1Global-Skills` (instalada en `.claude/skills/`): https://github.com/star23/Day1Global-Skills
- Eco3min, "The Liquidity Illusion — Net Liquidity Index (2003–2026)" y dataset S&P 500 vs Fed Balance Sheet: https://eco3min.fr/en/net-liquidity-index-dataset/
- Kunkel Capital, "Net Liquidity Cycles Decide Where Risk Assets Trend": https://kunkelcapital.com/blog/net-liquidity-cycles-risk-assets
- DollarLiquidity.com, "What Is Net Liquidity" y "TGA vs ONRRP": https://dollarliquidity.com/en/learn/what-is-net-liquidity
- GuruFocus, "Fed Net Liquidity" (Max Anderson): https://www.gurufocus.com/market/fed-net-liquidity-sp500
- New York Fed, "How SOFR Works", "A User's Guide to SOFR", "What Happens on Quarter-Ends in the Repo Market": https://www.newyorkfed.org/markets/reference-rates/sofr
- CME Group, "Is the SOFR Benchmark Becoming More Volatile?": https://www.cmegroup.com/articles/2025/is-the-sofr-benchmark-becoming-more-volatile.html
- Chairtham (Chatham Financial), "SOFR: A comprehensive guide": https://cf.com/insights/sofr-end-users-guide
- BIS, "The market turbulence and carry trade unwind of August 2024" (Bulletin 90): https://www.bis.org/publ/bisbull90.htm
- Reuters/AP/Goldman, explainers del yen carry (ago-2024).
- ICE Developer, "MOVE Index"; Convexity Maven (Harley Bassman) notas sobre implied vol y el MOVE.
- Kenmacro, "MOVE Index Explained — The Bond Vol Gauge": https://kenmacro.com/move-index-explained-bond-vol-traders-guide/
- ING THINK, "FX Daily: Joint yen intervention is a containment exercise" (03-ago-2026); CNBC, "Fed may be pulled into Bessent's effort to support Japan's yen" (2026).

> **Disclaimer**: análisis informativo y educativo. La liquidez es un factor más entre muchos (fundamentales, geopolitica, riesgo idiosincrático). Ningún indicador de este documento constituye asesoría financiera ni garantiza resultados.