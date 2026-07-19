import keyboard

print("Press q to quit")

while True:
    if keyboard.is_pressed("a"):
        print("A")
    if keyboard.is_pressed("q"):
        break