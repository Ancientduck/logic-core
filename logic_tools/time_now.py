from datetime import datetime

def main():
    now = datetime.now()
    formatted_now = now.strftime("%B %d, %Y, %I:%M %p")
    print(formatted_now)
    
if __name__ == "__main__":
    main()