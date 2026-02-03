import os
from datetime import date, timedelta
from database import SessionLocal
from models import Workplace, Employee, ShiftDefinition, WorkplaceWeights, EmployeeSettings, Assignment
from solver import ShiftOptimizer
from excel_writer import create_excel_report_from_db
from ortools.sat.python import cp_model


def get_next_sunday():
    """
    Calculates the date of the upcoming Sunday to align the schedule.
    """
    today = date.today()
    days_ahead = 6 - today.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return today + timedelta(days=days_ahead)


def save_results_to_db(session, results, workplace_id, start_date):
    """
    Clears old assignments and saves new ones with mapped dates.
    """
    # Remove existing assignments for this workplace to prevent duplicates
    session.query(Assignment).filter(Assignment.workplace_id == workplace_id).delete()

    for res in results:
        # Map solver day index (0-6) to actual calendar date
        assignment_date = start_date + timedelta(days=res["day_index"])

        assignment = Assignment(
            workplace_id=res["workplace_id"],
            employee_id=res["employee_id"],
            shift_id=res["shift_id"],
            date=assignment_date
        )
        session.add(assignment)
    session.commit()


def main():
    session = SessionLocal()
    workplace_name = "SL_HE"  # Match the name used in seed.py

    try:
        # 1. Fetch Environment from DB
        workplace = session.query(Workplace).filter(Workplace.name == workplace_name).first()
        if not workplace:
            print(f"Error: Workplace '{workplace_name}' not found. Please run seed.py first.")
            return

        # Prepare data for solver
        employees = [e for e in workplace.employees if e.is_active]
        shifts = workplace.shifts
        weights = session.query(WorkplaceWeights).filter(WorkplaceWeights.workplace_id == workplace.id).first()

        # Load specific employee contract settings
        emp_settings_dict = {
            s.employee_id: s for s in session.query(EmployeeSettings).filter(
                EmployeeSettings.employee_id.in_([e.id for e in employees])
            ).all()
        }

        print(f"--- System Ready: Starting Optimization for {workplace.name} ---")

        # 2. Execute Solver
        optimizer = ShiftOptimizer(
            workplace_id=workplace.id,
            employees=employees,
            shifts=shifts,
            weights=weights
        )
        status = optimizer.solve(emp_settings_dict)

        # 3. Handle Output
        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            print(f"✅ Solver Success! Objective: {optimizer.solver.ObjectiveValue()}")

            # Extract results and determine start date
            results = optimizer.get_results_as_dicts()
            start_date = get_next_sunday()

            # Persist to Database
            save_results_to_db(session, results, workplace.id, start_date)

            # Generate Visual Excel Report from the saved DB data
            create_excel_report_from_db(session, workplace.id, start_date)

        else:
            print("❌ Solver failed to find a valid solution.")

    except Exception as e:
        print(f"Critical Error: {e}")
    finally:
        session.close()


if __name__ == "__main__":
    main()