# main.py
import os
from ortools.sat.python import cp_model

# Import modules
import config
import optimizer
import excel_writer


def main():
    # --------------------------------------------------------
    # 1. Image Parsing Logic (Optional)
    # --------------------------------------------------------
    # Note: Since we moved to an Object-Oriented structure,
    # if image parsing is enabled, we need to inject the results
    # directly into the specific Employee objects.

    if config.ENABLE_IMAGE_PARSING:
        print(f"--- Image Mode Enabled: Parsing {config.IMAGE_FILENAME} ---")
        if os.path.exists(config.IMAGE_FILENAME):
            try:
                # Import only if needed
                from image_process.cv2_image_parser import ScheduleImageParser

                # Define employee order in image (Top -> Down) assuming it matches ID order
                img_employee_order = [emp.id for emp in config.EMPLOYEES]

                parser = ScheduleImageParser(config.IMAGE_FILENAME)
                # parse_tables returns list of tuples: (emp_id, day, shift)
                image_constraints = parser.parse_tables(img_employee_order)

                print(f"V Success: Extracted {len(image_constraints)} constraints from image.")

                # Inject constraints into Employee objects
                for emp_id, day, shift in image_constraints:
                    # Find the employee object with this ID
                    # (Assuming IDs match index for simplicity, but safety check added)
                    target_emp = next((e for e in config.EMPLOYEES if e.id == emp_id), None)
                    if target_emp:
                        target_emp.state.unavailable_shifts.append((day, shift))
                    else:
                        print(f"Warning: Image parser found constraint for unknown Employee ID {emp_id}")

            except ImportError:
                print("X Error: cv2_image_parser.py is missing or invalid.")
            except AttributeError:
                print("X Error: 'parse_tables' function not found.")
            except Exception as e:
                print(f"X General Error parsing image: {e}")
        else:
            print(f"X Error: File {config.IMAGE_FILENAME} not found.")
    else:
        print("--- Image Mode Disabled: Using manual config only ---")

    # --------------------------------------------------------
    # 2. Run Optimization
    # --------------------------------------------------------
    # The new optimizer signature only requires the employees list.
    # All constraints (manual assignments, history, unavailability) are already inside the objects.

    print("--- Building and Solving Model ---")
    solver, status, shift_vars = optimizer.build_and_solve_model(
        employees=config.EMPLOYEES
    )

    # --------------------------------------------------------
    # 3. Output Results
    # --------------------------------------------------------
    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        print(f"\n✅ Solution Found! Cost (Penalty): {solver.ObjectiveValue()}")

        # Pass the updated objects to the excel writer
        excel_writer.create_excel_schedule(
            solver=solver,
            shift_vars=shift_vars,
            employees=config.EMPLOYEES,
            num_days=config.NUM_DAYS,
            num_shifts=config.NUM_SHIFTS,
            shifts_per_day_demand=config.SHIFTS_PER_DAY_DEMAND
        )
    else:
        print("\n❌ No feasible solution found. Try relaxing constraints.")


if __name__ == "__main__":
    main()