import requests

token = '39866d45-1a55-4243-9157-827af91a9210'
headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

query = '''
query {
    project(id: "23436bb9-b566-41ab-98c7-a12cffa31369") {
        id
        name
        environments {
            edges {
                node {
                    id
                    name
                }
            }
        }
    }
}
'''

r = requests.post('https://backboard.railway.com/graphql/v2', headers=headers, json={'query': query})
print(r.json())
