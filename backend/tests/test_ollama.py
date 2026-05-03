# import requests

# res = requests.post(
#     "http://192.168.1.34:11434/api/generate",
#     json={
#         "model": "qwen3:4b-q4_K_M",
#         "prompt": "Explain APIs",
#         "stream": False   # ✅ IMPORTANT
#     }
# )

# print(res.json()["response"])

# import requests

# res = requests.post(
#     "http://192.168.1.34:11434/api/chat",
#     json={
#         "model": "qwen3:4b-q4_K_M",
#         "messages": [
#             {"role": "user", "content": "Hello"},
#             {"role": "assistant", "content": "Hi!"},
#             {"role": "user", "content": "Explain APIs"}
#         ],
#         "stream": False
#     }
# )

# print(res.json()["message"]["content"])

# import requests

# res = requests.get("http://192.168.1.34:11434/api/tags")

# print(res.json())


# import requests

# res = requests.post(
#     "http://192.168.1.34:11434/api/show",
#     json={"name": "qwen3:4b-q4_K_M"}
# )

# print(res.json())

# import requests

# res = requests.post(
#     "http://192.168.1.34:11434/api/pull",
#     json={"name": "mistral"}
# )

# print(res.json())

# import requests

# res = requests.delete(
#     "http://192.168.1.34:11434/api/delete",
#     json={"name": "mistral"}
# )

# print(res.json())

# import requests

# res = requests.post(
#     "http://192.168.1.34:11434/api/embeddings",
#     json={
#         "model": "qwen3:4b-q4_K_M",
#         "prompt": "API monitoring error handling"
#     }
# )

# print(res.json()["embedding"])


import requests
import json

res = requests.post(
    "http://192.168.1.34:11434/api/generate",
    json={
        "model": "qwen3:4b-q4_K_M",
        "prompt": "Do the RCA on thie error: 'Connection timeout after 30s'",
    },
    stream=True
)

for line in res.iter_lines():
    if line:
        data = json.loads(line)
        print(data.get("response", ""), end="", flush=True)