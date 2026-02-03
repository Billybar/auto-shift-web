from ortools.sat.python import cp_model
from models import Employee, ShiftDefinition, WorkplaceWeights, EmployeeSettings
from typing import List, Dict


class ConstraintManager:
    def __init__(self, model, shift_vars, employees, shifts, weights, num_days=7):
        self.model = model
        self.shift_vars = shift_vars
        self.employees = employees
        self.shifts = shifts
        self.weights = weights
        self.num_days = num_days

    def apply_all_constraints(self, employee_settings: Dict[int, EmployeeSettings], employee_states: Dict[int, any]):
        """
        Main entry point.
        :param employee_settings: Dictionary mapping employee_id to its settings from DB.
        :param employee_states: Dictionary mapping employee_id to its dynamic state (last week history).
        """
        self._add_hard_constraints(employee_settings)
        return self._get_objective_terms(employee_settings, employee_states)

    def _add_hard_constraints(self, employee_settings):
        # ... (אילוצי הכיסוי ומשמרת אחת ביום כפי שכתבנו קודם)

        for emp in self.employees:
            settings = employee_settings.get(emp.id)
            if settings:
                # אילוץ קשיח: מקסימום משמרות בשבוע מה-DB
                all_emp_shifts = [self.shift_vars[(emp.id, d, s.id)] for d in range(self.num_days) for s in self.shifts]
                self.model.Add(sum(all_emp_shifts) <= settings.max_shifts_per_week)
                # אילוץ קשיח: מינימום משמרות בשבוע מה-DB
                self.model.Add(sum(all_emp_shifts) >= settings.min_shifts_per_week)

    def _get_objective_terms(self, employee_settings, employee_states):
        objective_terms = []
        w = {
            'REST_GAP': self.weights.weight_min_rest,
            'TARGET_SHIFTS': self.weights.weight_fairness,  # או weight_preference לפי בחירתך
        }

        for emp in self.employees:
            state = employee_states.get(emp.id)
            settings = employee_settings.get(emp.id)

            # --- 1. המשכיות מסופ"ש קודם (Previous Week Rest Gap) ---
            if state:
                # זיהוי ה-IDs של משמרות בוקר וצהריים (נניח לפי סדר הופעתם ב-DB)
                morning_shift_id = self.shifts[0].id
                noon_shift_id = self.shifts[1].id if len(self.shifts) > 1 else None

                # אם עבד בשבת בצהריים -> קנס על עבודה בראשון בבוקר
                if state.worked_last_sat_noon:
                    objective_terms.append(self.shift_vars[(emp.id, 0, morning_shift_id)] * w['REST_GAP'])

                # אם עבד בשבת בלילה -> קנס על עבודה בראשון צהריים
                if state.worked_last_sat_night and noon_shift_id:
                    objective_terms.append(self.shift_vars[(emp.id, 0, noon_shift_id)] * w['REST_GAP'])

            # --- 2. יעד משמרות (Target Shifts) ---
            if settings:
                # במידה ואין עמודת target_shifts ב-DB, ניתן להשתמש בממוצע בין מינימום למקסימום
                target = getattr(settings, 'target_shifts',
                                 (settings.min_shifts_per_week + settings.max_shifts_per_week) // 2)

                all_emp_shifts = [self.shift_vars[(emp.id, d, s.id)] for d in range(self.num_days) for s in self.shifts]
                total_worked = sum(all_emp_shifts)

                # חישוב המרחק מהיעד (Delta)
                delta = self.model.NewIntVar(0, self.num_days, f'delta_target_e{emp.id}')
                self.model.Add(total_worked - target <= delta)
                self.model.Add(target - total_worked <= delta)
                objective_terms.append(delta * w['TARGET_SHIFTS'])

        return objective_terms