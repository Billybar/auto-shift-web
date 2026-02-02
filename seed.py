from database import SessionLocal, init_db
from models import (Workplace, Employee, ShiftDefinition,
                    EmployeeSettings, WorkplaceWeights, ConstraintType, WeeklyConstraint)
from datetime import date


def seed_data():
    # 1. Initialize the database and create tables
    init_db()

    session = SessionLocal()

    try:
        # Check if the data already exists to avoid duplicates
        existing_workplace = session.query(Workplace).filter_by(name="Chocolate Factory").first()
        if existing_workplace:
            print("Database already seeded. Skipping...")
            return

        # 2. Create a Workplace entity
        factory = Workplace(name="Chocolate Factory", num_days_in_cycle=7)
        session.add(factory)
        session.flush()  # Flush to generate the ID for the factory

        # 3. Define Workplace Optimization Weights
        weights = WorkplaceWeights(
            workplace_id=factory.id,
            weight_preference=15,
            weight_fairness=10,
            weight_min_rest=50  # High priority on rest periods
        )
        session.add(weights)

        # 4. Define Shift Types (Definitions)
        morning = ShiftDefinition(workplace_id=factory.id, shift_name="Morning", min_staff=2)
        evening = ShiftDefinition(workplace_id=factory.id, shift_name="Evening", min_staff=2)
        session.add_all([morning, evening])
        session.flush()

        # 5. Create Employees and their specific contract settings
        emp1 = Employee(workplace_id=factory.id, name="Israel Israeli")
        emp2 = Employee(workplace_id=factory.id, name="Dana Levi")
        session.add_all([emp1, emp2])
        session.flush()

        settings_emp1 = EmployeeSettings(
            employee_id=emp1.id,
            min_shifts_per_week=3,
            max_shifts_per_week=5
        )
        settings_emp2 = EmployeeSettings(
            employee_id=emp2.id,
            min_shifts_per_week=2,
            max_shifts_per_week=4
        )
        session.add_all([settings_emp1, settings_emp2])

        # 6. Add a Weekly Constraint example
        # Dana cannot work on the morning shift of a specific date
        constraint = WeeklyConstraint(
            employee_id=emp2.id,
            shift_id=morning.id,
            date=date(2026, 2, 8),  # Next Sunday
            constraint_type=ConstraintType.CANNOT_WORK
        )
        session.add(constraint)

        # Commit all changes to the database
        session.commit()
        print("Seed data populated successfully!")

    except Exception as e:
        # Rollback in case of any error to maintain DB integrity
        session.rollback()
        print(f"Error during seeding: {e}")
    finally:
        session.close()


if __name__ == "__main__":
    seed_data()