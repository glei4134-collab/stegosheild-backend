"""
Railway API 客户端 - 用于自动化部署 StegoShield 后端
"""

import requests
import json
import os
import time

RAILWAY_API_URL = "https://backboard.railway.com/graphql/v2"


class RailwayClient:
    def __init__(self, token: str):
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

    def graphql(self, query: str, variables: dict = None) -> dict:
        """执行 GraphQL 查询"""
        response = requests.post(
            RAILWAY_API_URL,
            headers=self.headers,
            json={"query": query, "variables": variables or {}}
        )
        response.raise_for_status()
        result = response.json()
        if "errors" in result:
            raise Exception(f"GraphQL Error: {result['errors']}")
        return result.get("data", {})

    def get_me(self) -> dict:
        """获取当前用户信息"""
        query = """
        query {
            me {
                id
                name
                email
            }
        }
        """
        return self.graphql(query)

    def get_workspace(self, workspace_id: str) -> dict:
        """获取工作空间信息"""
        query = """
        query($workspaceId: String!) {
            workspace(id: $workspaceId) {
                id
                name
                projects {
                    edges {
                        node {
                            id
                            name
                        }
                    }
                }
            }
        }
        """
        return self.graphql(query, {"workspaceId": workspace_id})

    def create_project(self, name: str) -> dict:
        """创建新项目"""
        query = """
        mutation($name: String!) {
            projectCreate(input: {name: $name}) {
                id
                name
            }
        }
        """
        return self.graphql(query, {"name": name})

    def create_service_from_github(
        self,
        project_id: str,
        repo_owner: str,
        repo_name: str,
        branch: str = "main"
    ) -> dict:
        """从 GitHub 仓库创建服务"""
        query = """
        mutation($projectId: String!, $repoOwner: String!, $repoName: String!, $branch: String!) {
            serviceCreateFromGitHub(input: {
                projectId: $projectId,
                repoOwner: $repoOwner,
                repoName: $repoName,
                branch: $branch
            }) {
                id
                name
                projectId
            }
        }
        """
        return self.graphql(query, {
            "projectId": project_id,
            "repoOwner": repo_owner,
            "repoName": repo_name,
            "branch": branch
        })

    def deploy_service(self, service_id: str, environment_id: str) -> dict:
        """触发服务部署"""
        query = """
        mutation($serviceId: String!, $environmentId: String!) {
            deploymentCreate(input: {
                serviceId: $serviceId,
                environmentId: $environmentId
            }) {
                id
            }
        }
        """
        return self.graphql(query, {
            "serviceId": service_id,
            "environmentId": environment_id
        })

    def get_deployment_status(self, deployment_id: str) -> dict:
        """获取部署状态"""
        query = """
        query($id: String!) {
            deployment(id: $id) {
                id
                status
                createdAt
                updatedAt
            }
        }
        """
        return self.graphql(query, {"id": deployment_id})

    def get_service_deployments(self, service_id: str, environment_id: str) -> dict:
        """获取服务部署列表"""
        query = """
        query($serviceId: String!, $environmentId: String!) {
            deployments(serviceId: $serviceId, environmentId: $environmentId, first: 1) {
                edges {
                    node {
                        id
                        status
                        createdAt
                        meta {
                            commitMessage
                            branch
                        }
                    }
                }
            }
        }
        """
        return self.graphql(query, {
            "serviceId": service_id,
            "environmentId": environment_id
        })

    def wait_for_deployment(self, deployment_id: str, timeout: int = 300) -> dict:
        """等待部署完成"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            status = self.get_deployment_status(deployment_id)
            deployment = status.get("deployment", {})
            current_status = deployment.get("status", "")

            print(f"部署状态: {current_status}")

            if current_status in ["SUCCESS", "FAILED", "CRASHED", "REMOVED"]:
                return status

            time.sleep(5)

        raise TimeoutError(f"部署超时 ({timeout}秒)")

    def get_project_environment(self, project_id: str) -> str:
        """获取项目默认环境ID"""
        query = """
        query($projectId: String!) {
            project(id: $projectId) {
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
        """
        data = self.graphql(query, {"projectId": project_id})
        environments = data.get("project", {}).get("environments", {}).get("edges", [])
        if environments:
            return environments[0]["node"]["id"]
        raise Exception("未找到环境")


def deploy_to_railway(token: str, repo_owner: str, repo_name: str, project_name: str = None):
    """
    完整部署流程

    Args:
        token: Railway API Token
        repo_owner: GitHub 仓库所有者
        repo_name: GitHub 仓库名称
        project_name: 项目名称（可选）
    """
    client = RailwayClient(token)

    if project_name is None:
        project_name = f"stegosheild-{repo_name}"

    print("=" * 50)
    print("Railway 部署工具")
    print("=" * 50)

    # 1. 获取用户信息
    print("\n[1/6] 获取用户信息...")
    me = client.get_me()
    print(f"用户: {me['me']['name']} ({me['me']['email']})")

    # 2. 创建项目
    print(f"\n[2/6] 创建项目: {project_name}...")
    project = client.create_project(project_name)
    project_id = project["projectCreate"]["id"]
    print(f"项目ID: {project_id}")

    # 3. 等待项目初始化
    print("\n[3/6] 等待项目初始化...")
    time.sleep(3)

    # 4. 获取环境ID
    print("\n[4/6] 获取环境信息...")
    environment_id = client.get_project_environment(project_id)
    print(f"环境ID: {environment_id}")

    # 5. 从 GitHub 创建服务
    print(f"\n[5/6] 从 GitHub 创建服务: {repo_owner}/{repo_name}...")
    service = client.create_service_from_github(
        project_id=project_id,
        repo_owner=repo_owner,
        repo_name=repo_name,
        branch="main"
    )
    service_id = service["serviceCreateFromGitHub"]["id"]
    print(f"服务ID: {service_id}")

    # 6. 触发部署
    print("\n[6/6] 触发部署...")
    deployment = client.deploy_service(service_id, environment_id)
    deployment_id = deployment["deploymentCreate"]["id"]
    print(f"部署ID: {deployment_id}")

    # 7. 等待部署完成
    print("\n等待部署完成...")
    result = client.wait_for_deployment(deployment_id)

    final_status = result["deployment"]["status"]
    if final_status == "SUCCESS":
        print("\n" + "=" * 50)
        print("✅ 部署成功!")
        print(f"项目ID: {project_id}")
        print(f"服务ID: {service_id}")
        print(f"部署ID: {deployment_id}")
        print("=" * 50)
    else:
        print(f"\n❌ 部署失败: {final_status}")
        return None

    return {
        "project_id": project_id,
        "service_id": service_id,
        "deployment_id": deployment_id
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 4:
        print("用法: python railway_deploy.py <API_TOKEN> <GITHUB_OWNER> <GITHUB_REPO> [项目名称]")
        print("\n示例:")
        print("  python railway_deploy.py rln_xxx yourusername stegosheild-backend")
        print("  python railway_deploy.py rln_xxx yourusername stegosheild-backend MyCustomProject")
        print("\n获取 API Token:")
        print("  1. 访问 https://railway.com/dashboard/tokens")
        print("  2. 点击 'New Token'")
        print("  3. 复制 token (以 rln_ 开头)")
        sys.exit(1)

    token = sys.argv[1]
    owner = sys.argv[2]
    repo = sys.argv[3]
    project_name = sys.argv[4] if len(sys.argv) > 4 else None

    try:
        result = deploy_to_railway(token, owner, repo, project_name)
        if result:
            print(f"\n后端地址: https://{project_name or repo}.railway.app")
    except Exception as e:
        print(f"\n错误: {e}")
        sys.exit(1)
