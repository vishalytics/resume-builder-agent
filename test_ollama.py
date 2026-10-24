import ollama

response = ollama.chat(
    model="qwen3:8b",
    messages=[
        {
            "role": "user",
            "content": "In 5 bullet points, explain what a good Program Manager does."
        }
    ]
)

print(response["message"]["content"])