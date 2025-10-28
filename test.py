from faker import Faker
import re
faker = Faker("ru_RU")
faker_replace = {
            "name": lambda: faker.name(),
            "address": lambda: faker.address(),
            "phone_number": lambda: faker.phone_number(),
            "company": lambda: faker.company(),
        }
def parse_comment(comment, refind):
    for i in refind:
        comment = comment.replace(
            i,
            faker_replace[i.replace("{{", "").replace("}}", "")](),
        )
        print("{{" + i + "}}",
            faker_replace[i.replace("{{", "").replace("}}", "")])
    return comment
print(parse_comment("{{name}} привет", re.findall(r"{{\w+}}","{{name}} привет")))