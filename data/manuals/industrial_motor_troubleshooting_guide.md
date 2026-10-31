# Non-Confidential Industrial Electric Motor Troubleshooting & Reliability Manual
**Document Reference:** STD-ELEC-2026-REV4  
**Classification:** Standard Engineering Practice (Public / Non-Confidential)  
**Applicability:** Class II & Class III Medium Induction Motors (10 kW to 45 kW)  
**Target Equipment:** `MOTOR-PUMP-01` (Coolant Pump), `MOTOR-CONV-02` (Conveyor), `MOTOR-COMP-03` (Compressor)

---

## 1. Engineering Scope and Equipment Baselines

This technical standard establishes empirical vibration limits, thermal operating thresholds, electrical power quality criteria, and safety procedures for continuous-duty industrial induction motors.

### Monitored Motor Asset Baseline Specifications
- **MOTOR-PUMP-01 (Primary Coolant Centrifugal Pump Motor):**
  - Rated Power: 15.0 kW | 400V/230V 3-Phase AC | Rated Current: 28.0 A
  - Nominal Speed: 1450 RPM | Discharge Pressure: 4.2 bar
  - Normal Baseline: Temp 52°C, Vibration 1.8 mm/s RMS, Current 26.5 A, Noise 68 dB
- **MOTOR-CONV-02 (Heavy Raw Material Incline Belt Conveyor Motor):**
  - Rated Power: 11.0 kW | 400V/230V 3-Phase AC | Rated Current: 21.0 A
  - Nominal Speed: 1470 RPM
  - Normal Baseline: Temp 58°C, Vibration 2.2 mm/s RMS, Current 19.5 A, Noise 72 dB
- **MOTOR-COMP-03 (High-Pressure Rotary Twin-Screw Compressor Motor):**
  - Rated Power: 22.0 kW | 400V/230V 3-Phase AC | Rated Current: 41.0 A
  - Nominal Speed: 2960 RPM | Discharge Pressure: 7.5 bar
  - Normal Baseline: Temp 65°C, Vibration 2.5 mm/s RMS, Current 38.0 A, Noise 76 dB

---

## 2. Mechanical Vibration Diagnostics (ISO 10816-3 Criteria)

Overall vibration velocity RMS ($10\text{ Hz}$ to $1000\text{ Hz}$) indicates mechanical machine health:

| Vibration Velocity (mm/s RMS) | ISO 10816-3 Severity Zone | Operational Status & Action |
| :--- | :--- | :--- |
| **0.00 to 2.80 mm/s** | **Zone A / B (Good / Satisfactory)** | Newly commissioned or normal operational condition. No action required. |
| **2.81 to 4.50 mm/s** | **Zone C (Warning Threshold)** | Mechanical degradation detected. Schedule shaft alignment and re-greasing. |
| **> 7.10 mm/s** | **Zone D (Critical Shutdown Limit)** | Severe machine damage imminent. Trip equipment and perform emergency inspection. |

### Failure Mechanism Signatures:
1. **Mechanical Unbalance (1X RPM Peak):** Caused by dirt accumulation on fan impeller or eccentric rotor mass.
2. **Coupling Misalignment (2X RPM Peak with Axial Vibration):** Angular or offset misalignment between motor shaft and driven gearbox or pump coupling.
3. **Rolling Element Bearing Degradation (High Frequency > 1 kHz Peaks):**
   - Ball Pass Frequency Inner Race (BPFI)
   - Ball Pass Frequency Outer Race (BPFO)
   - Micro-spalling in raceway requires replacement using SKF 6308 / 6310 deep-groove bearings.

---

## 3. Thermal Overheating & Insulation Protection (NEMA MG-1)

Induction motors in continuous industrial service are rated with Class F insulation ($155^\circ\text{C}$ maximum allowable hot-spot temperature), designed for a nominal casing temperature rise not exceeding $80^\circ\text{C}$ over $40^\circ\text{C}$ ambient.

### Thermal Operating Boundaries:
- **Continuous Safe Zone:** $30^\circ\text{C}$ to $75^\circ\text{C}$ casing temperature.
- **Warning Threshold ($\ge 75^\circ\text{C}$):** Elevated thermal gradient. Inspect cooling fan shroud, clean air cowl of airborne lint, and verify grease discharge port is unobstructed.
- **Critical Threshold ($\ge 90^\circ\text{C}$):** Immediate shutdown advised. Operating above $90^\circ\text{C}$ reduces winding insulation lifetime by 50% for every $10^\circ\text{C}$ increase (Arrhenius thermal degradation law).

---

## 4. Electrical Power Quality & Overload Anomalies

### 4.1 Phase Overcurrent Criteria
- **Normal Load Range:** $80\%$ to $100\%$ of rated full-load amperes (FLA).
- **Warning Limit:** Amperage $\ge 115\%$ FLA for more than 15 seconds. Indicates mechanical drag or conveyor overburden.
- **Critical Limit:** Amperage $\ge 135\%$ FLA. Imminent thermal trip or locked rotor condition.

### 4.2 Supply Voltage Sags & Phase Imbalance
- Nominal Voltage: $230\text{ V}$ line-to-neutral ($400\text{ V}$ line-to-line 3-phase).
- **Voltage Sag Warning:** Line voltage drops below $207\text{ V}$ ($-10\%$).
- **Voltage Sag Critical:** Line voltage drops below $195\text{ V}$ ($-15\%$).
- *Physical Law:* Induction motor shaft torque is proportional to voltage squared ($T \propto V^2$). Under voltage sag, the motor draws increased current to sustain load torque, accelerating thermal buildup.
- *Phase Voltage Imbalance Limit:* A $1\%$ voltage unbalance between phases induces a $6\%$ to $10\%$ current unbalance, producing localized stator hot spots.

---

## 5. Acoustic Noise, Cavitation & Compound Seizure

### 5.1 Centrifugal Pump Cavitation (`MOTOR-PUMP-01`)
- **Phenomenon:** When fluid static pressure drops below liquid vapor pressure, vapor bubbles form and collapse violently against pump impeller vanes.
- **Observable Symptoms:** Erratic rattling or marble-like acoustic noise ($\ge 88\text{ dB}$), sudden discharge pressure drop below $3.0\text{ bar}$, and localized vibration spikes.
- **Corrective Procedure:** Clear suction strainer, verify suction isolation valve is 100% open, check Net Positive Suction Head Available (NPSHa), and purge air pockets.

### 5.2 Compound Bearing Failure
- **Definition:** Simultaneous occurrence of high vibration ($\ge 5.5\text{ mm/s}$) **AND** elevated casing temperature ($\ge 80^\circ\text{C}$).
- **Mechanism:** Severe boundary lubrication breakdown resulting in microscopic metal asperities welding under load.
- **Emergency Mandate:** Immediate shutdown. Do not attempt restart without complete mechanical bearing assembly overhaul.

---

## 6. Mandatory Safety & Maintenance Procedures (OSHA 1910.147)

1. **Lockout-Tagout (LOTO):** Always isolate MCC circuit breakers, apply padlocks and warning tags, and test for zero electrical potential with a calibrated multimeter before physical contact.
2. **Thermal PPE:** Use thermal gloves when handling motor casing or bearing housings exceeding $60^\circ\text{C}$.
3. **Shaft Alignment Protocol:** Use dual-dial or laser alignment systems; align within $0.05\text{ mm}$ tolerance.
4. **Foundation Bolt Torquing:** Inspect foundation anchor bolts annually and torque to $85\text{ Nm}$.
