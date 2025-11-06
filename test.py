class Calculator:
    @staticmethod
    def add(x, y):
        return x + y

    @staticmethod
    def multiply(x, y):
        return x * y

# Calling static methods directly on the class
result_add = Calculator.add(5, 3)
print(f"Addition result: {result_add}")

result_multiply = Calculator.multiply(4, 6)
print(f"Multiplication result: {result_multiply}")

# Calling static methods on an instance (though not necessary)
my_calc = Calculator()
instance_add_result = my_calc.add(10, 2)
print(f"Instance addition result: {instance_add_result}")