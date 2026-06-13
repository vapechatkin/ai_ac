from agent import Agent


def main():
    agent = Agent()

    print("GigaChat Agent started")
    print("Введите 'exit' для выхода\n")

    while True:
        user_input = input("Вы: ")

        if user_input.lower() == "exit":
            print("Завершение программы...")
            break

        try:
            answer = agent.ask(user_input)

            print(f"\nАгент: {answer}\n")

        except Exception as error:
            print(f"\nОшибка: {error}\n")


if __name__ == "__main__":
    main()
