import requests

try:
    res = requests.post("http://localhost:5000/api/mentor", json={
        "question": "What is NAND gate?",
        "company": "HCL"
    })
    print("Status:", res.status_code)
    print("Response:", res.json())
except Exception as e:
    print("Error:", e)