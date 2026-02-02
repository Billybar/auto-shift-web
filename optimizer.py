from ortools.sat.python import cp_model
import config


def build_and_solve_model(employees):
    num_employees = len(employees)
    num_days = config.NUM_DAYS
    num_shifts = config.NUM_SHIFTS

    model = cp_model.CpModel()

    # --- Variables ---
    shift_vars = {}
    for e in range(num_employees):
        for d in range(num_days):
            for s in range(num_shifts):
                shift_vars[(e, d, s)] = model.NewBoolVar(f'shift_{e}_{d}_{s}')

    # ----------------------- #
    # --- Hard Constraints ---#
    # ----------------------- #
    # A. Demand (Exact number of workers per shift)
    for d in range(num_days):
        for s in range(num_shifts):
            model.Add(sum(shift_vars[(e, d, s)] for e in range(num_employees) if
                          employees[e].is_active) == config.SHIFTS_PER_DAY_DEMAND)

    # LOOP PER EMPLOYEE
    for e_idx, emp in enumerate(employees):

        # Skip inactive employees entirely (force all their shifts to 0)
        if not emp.is_active:
            for d in range(num_days):
                for s in range(num_shifts):
                    model.Add(shift_vars[(e_idx, d, s)] == 0)
            continue

        # B. Prevent back-to-back shifts (Global logic, same as before)
        for total_s in range(num_days * num_shifts - 1):
            day = total_s // num_shifts
            shift = total_s % num_shifts
            next_total_s = total_s + 1
            next_day = next_total_s // num_shifts
            next_shift = next_total_s % num_shifts
            model.Add(shift_vars[(e_idx, day, shift)] + shift_vars[(e_idx, next_day, next_shift)] <= 1)

        # Assign unavailable_requests
        for day, shift in emp.state.unavailable_shifts:
            model.Add(shift_vars[(e_idx, day, shift)] == 0)

        if emp.state.worked_last_sat_night:
            model.Add(shift_vars[(e_idx, 0, 0)] == 0)  # Cannot work Sunday morning

        for day, shift in emp.state.forced_shifts:
            # internal validation
            if (day, shift) in emp.state.unavailable_shifts:
                raise ValueError(
                    f"CRITICAL ERROR: {emp.name} is forced to work (Day {day}, Shift {shift}) but is marked unavailable!")

            print(f"Forcing assignment: {emp.name} -> Day {day} Shift {shift}")
            model.Add(shift_vars[(e_idx, day, shift)] == 1)

        # F. Max Streak ( uses 'emp.state.history_streak')
        work_days_vars = []
        for d in range(num_days):
            is_working_day = model.NewBoolVar(f'working_day_{e_idx}_{d}')
            model.Add(sum(shift_vars[(e_idx, d, s)] for s in range(num_shifts)) > 0).OnlyEnforceIf(is_working_day)
            model.Add(sum(shift_vars[(e_idx, d, s)] for s in range(num_shifts)) == 0).OnlyEnforceIf(
                is_working_day.Not())
            work_days_vars.append(is_working_day)

        streak = emp.state.history_streak
        if streak > 0:
            limit = 7 - streak
            if limit <= num_days and limit > 0:
                model.Add(sum(work_days_vars[0:limit]) < limit)
        if streak == 0:
            model.Add(sum(work_days_vars) < 7)

        # G. Max one shift per day (Standard logic)
        for d in range(num_days):
            model.Add(sum(shift_vars[(e_idx, d, s)] for s in range(num_shifts)) <= 1)

        shifts_flat = [shift_vars[(e_idx, d, s)] for d in range(num_days) for s in range(num_shifts)]
        model.Add(sum(shifts_flat) <= emp.prefs.max_shifts)

    # -------------------------------------- #
    # --- Soft Constraints (Optimization) ---#
    # -------------------------------------- #
    w = config.WEIGHTS
    objective_terms = []

    for e_idx, emp in enumerate(employees):
        if not emp.is_active: continue

        # Helpers
        morning_shifts = [shift_vars[(e_idx, d, 0)] for d in range(num_days)]
        evening_shifts = [shift_vars[(e_idx, d, 1)] for d in range(num_days)]
        night_shifts = [shift_vars[(e_idx, d, 2)] for d in range(num_days)]
        emp_shifts = morning_shifts + evening_shifts + night_shifts

        # Max Constraints
        excess_nights = model.NewIntVar(0, 7, f'excess_nights_{e_idx}')
        model.Add(sum(night_shifts) <= emp.prefs.max_nights + excess_nights)
        objective_terms.append(excess_nights * w['MAX_NIGHTS'])

        excess_mornings = model.NewIntVar(0, 7, f'excess_mornings_{e_idx}')
        model.Add(sum(morning_shifts) <= emp.prefs.max_mornings + excess_mornings)
        objective_terms.append(excess_mornings * w['MAX_MORNINGS'])

        excess_evenings = model.NewIntVar(0, 7, f'excess_evenings_{e_idx}')
        model.Add(sum(evening_shifts) <= emp.prefs.max_evenings + excess_evenings)
        objective_terms.append(excess_evenings * w['MAX_EVENINGS'])

        # Min Constraints
        shortage_nights = model.NewIntVar(0, 7, f'shortage_nights_{e_idx}')
        model.Add(sum(night_shifts) + shortage_nights >= emp.prefs.min_nights)
        objective_terms.append(shortage_nights * w['MIN_NIGHTS'])

        shortage_mornings = model.NewIntVar(0, 7, f'shortage_mornings_{e_idx}')
        model.Add(sum(morning_shifts) + shortage_mornings >= emp.prefs.min_mornings)
        objective_terms.append(shortage_mornings * w['MIN_MORNINGS'])

        shortage_evenings = model.NewIntVar(0, 7, f'shortage_evenings_{e_idx}')
        model.Add(sum(evening_shifts) + shortage_evenings >= emp.prefs.min_evenings)
        objective_terms.append(shortage_evenings * w['MIN_EVENINGS'])

        # Logic and Rest (Consecutive Nights)
        # 1. Standard check within the current week (Sunday to Saturday)
        for d in range(num_days - 2):
            is_three_nights = model.NewBoolVar(f'3nights_{e_idx}_{d}')
            model.AddBoolAnd([
                shift_vars[(e_idx, d, 2)],
                shift_vars[(e_idx, d + 1, 2)],
                shift_vars[(e_idx, d + 2, 2)]
            ]).OnlyEnforceIf(is_three_nights)

            model.AddBoolOr([
                shift_vars[(e_idx, d, 2)].Not(),
                shift_vars[(e_idx, d + 1, 2)].Not(),
                shift_vars[(e_idx, d + 2, 2)].Not()
            ]).OnlyEnforceIf(is_three_nights.Not())

            objective_terms.append(is_three_nights * w['CONSECUTIVE_NIGHTS'])

        # 2. HIDDEN SEQUENCES: Check continuation from last Friday/Saturday

        # Case A: Worked Friday Night AND Saturday Night -> Penalize Sunday Night
        if emp.state.worked_last_fri_night and emp.state.worked_last_sat_night:
            is_3rd_night_sun = model.NewBoolVar(f'3nights_cont_sun_{e_idx}')
            # If they work Sunday Night (Day 0, Shift 2), it's the 3rd consecutive night
            model.Add(shift_vars[(e_idx, 0, 2)] == 1).OnlyEnforceIf(is_3rd_night_sun)
            model.Add(shift_vars[(e_idx, 0, 2)] == 0).OnlyEnforceIf(is_3rd_night_sun.Not())
            objective_terms.append(is_3rd_night_sun * w['CONSECUTIVE_NIGHTS'])

        # Case B: Worked ONLY Saturday Night -> Penalize Sun+Mon sequence
        elif emp.state.worked_last_sat_night:
            is_3night_sequence_start = model.NewBoolVar(f'3nights_cont_sun_mon_{e_idx}')
            # If they work Sunday AND Monday nights, it's the 3rd night in a row
            model.AddBoolAnd([
                shift_vars[(e_idx, 0, 2)],
                shift_vars[(e_idx, 1, 2)]
            ]).OnlyEnforceIf(is_3night_sequence_start)

            model.AddBoolOr([
                shift_vars[(e_idx, 0, 2)].Not(),
                shift_vars[(e_idx, 1, 2)].Not()
            ]).OnlyEnforceIf(is_3night_sequence_start.Not())
            objective_terms.append(is_3night_sequence_start * w['CONSECUTIVE_NIGHTS'])

        # Rest Gap
        for total_s in range(num_days * num_shifts - 2):
            day = total_s // num_shifts
            shift = total_s % num_shifts
            t_total_s = total_s + 2
            t_day = t_total_s // num_shifts
            t_shift = t_total_s % num_shifts
            both_working = model.NewBoolVar(f'bad_gap_{e_idx}_{total_s}')
            model.AddBoolAnd([shift_vars[(e_idx, day, shift)], shift_vars[(e_idx, t_day, t_shift)]]).OnlyEnforceIf(
                both_working)
            model.AddBoolOr(
                [shift_vars[(e_idx, day, shift)].Not(), shift_vars[(e_idx, t_day, t_shift)].Not()]).OnlyEnforceIf(
                both_working.Not())
            objective_terms.append(both_working * w['REST_GAP'])

        # CHANGE 10: Previous week rest gap using 'emp.state'
        if emp.state.worked_last_sat_noon:
            objective_terms.append(shift_vars[(e_idx, 0, 0)] * w['REST_GAP'])
        if emp.state.worked_last_sat_night:
            objective_terms.append(shift_vars[(e_idx, 0, 1)] * w['REST_GAP'])

        # Target Shifts using 'emp.prefs'
        total_worked = sum(emp_shifts)
        delta = model.NewIntVar(0, 21, f'delta_target_{e_idx}')
        model.Add(total_worked - emp.prefs.target_shifts <= delta)
        model.Add(emp.prefs.target_shifts - total_worked <= delta)
        objective_terms.append(delta * w['TARGET_SHIFTS'])

    # --- Solve ---
    model.Minimize(sum(objective_terms))
    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    return solver, status, shift_vars