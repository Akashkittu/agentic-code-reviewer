import os

API_KEY = "sk_test_fake_key_123"


def hello(name):
    # TODO: improve greeting validation
    return "Hello " + name


def dangerous_command(user_input):
    os.system("echo " + user_input)


def dangerous_eval(user_input):
    return eval(user_input)


if __name__ == "__main__":
    print(hello("Akash"))