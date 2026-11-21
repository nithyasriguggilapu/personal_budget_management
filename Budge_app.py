class BudgetApp:
    def __init__(self):
        self.income = 0.0
        self.expenses = []

    def add_income(self):
        amount = float(input("Enter income amount: "))
        self.income += amount
        print("Income added successfully!\n")

    def add_expense(self):
        category = input("Enter expense category: ")
        amount = float(input("Enter expense amount: "))
        self.expenses.append({"category": category, "amount": amount})
        print("Expense added successfully!\n")

    def view_balance(self):
        total_expenses = sum(exp["amount"] for exp in self.expenses)
        balance = self.income - total_expenses
        print(f"Total Income: ${self.income:.2f}")
        print(f"Total Expenses: ${total_expenses:.2f}")
        print(f"Remaining Balance: ${balance:.2f}\n")

    def expense_summary(self):
        if not self.expenses:
            print("No expenses recorded.\n")
            return

        summary = {}
        for exp in self.expenses:
            summary[exp["category"]] = summary.get(exp["category"], 0) + exp["amount"]

        print("Expense Summary by Category:")
        for category, amount in summary.items():
            print(f"{category}: ${amount:.2f}")
        print()

    def menu(self):
        while True:
            print("====== Budget App ======")
            print("1. Add Income")
            print("2. Add Expense")
            print("3. View Balance")
            print("4. Expense Summary")
            print("5. Exit")

            choice = input("Choose an option (1-5): ")

            if choice == "1":
                self.add_income()
            elif choice == "2":
                self.add_expense()
            elif choice == "3":
                self.view_balance()
            elif choice == "4":
                self.expense_summary()
            elif choice == "5":
                print("Thank you for using Budget App. Goodbye!")
                break
            else:
                print("Invalid choice. Please try again.\n")


# Run the application
if __name__ == "__main__":
    app = BudgetApp()
    app.menu()