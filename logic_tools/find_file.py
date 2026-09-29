import requests
import re

def get_file_path(filename):
    try:
        url = f"http://127.0.0.1:80/?search={filename}"
        response = requests.get(url)
        
        if response.status_code == 200:
            full_paths = re.findall(r'href="/([^"]*)"', response.text)
            matches = []
            for path in full_paths:
                if '?' in path:
                    continue
                
                decoded_path = path.replace('%20', ' ').replace('%3A', ':').lstrip('/')
                if filename.lower() in decoded_path.lower():
                    matches.append(decoded_path)
            
            if matches:
                return "\n".join(matches)
            return "No matching files found sir."
        else:
            return f"Server error: {response.status_code}"
            
    except Exception as e:
        return f"Error: {e}"

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        print(get_file_path(query))
    else:
        print("Please provide a filename as an argument sir.")
