#!/usr/bin/env python3
"""
Test script to verify admin dashboard functionality
"""

import requests
import json

# Test admin login
def test_admin_login():
    print("Testing admin login...")
    url = "http://localhost:8000/api/login"
    payload = {
        "username": "AdminMIS",
        "password": "mis123"
    }
    headers = {"Content-Type": "application/json"}
    
    try:
        response = requests.post(url, data=json.dumps(payload), headers=headers)
        if response.status_code == 200:
            data = response.json()
            if data.get("success") and data.get("isAdmin"):
                print("✓ Admin login successful")
                return data.get("token")
            else:
                print("✗ Admin login failed:", data.get("message"))
        else:
            print("✗ Admin login failed with status code:", response.status_code)
    except Exception as e:
        print("✗ Admin login error:", str(e))
    
    return None

# Test admin metrics endpoint
def test_admin_metrics(token):
    print("Testing admin metrics endpoint...")
    url = "http://localhost:8000/api/admin/metrics"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            print("✓ Admin metrics retrieved successfully")
            print("  Users:", data.get("users"))
            print("  Chats:", data.get("chats"))
            print("  Active Users:", data.get("active_users"))
            print("  Server Status:", data.get("server_status"))
        else:
            print("✗ Admin metrics failed with status code:", response.status_code)
    except Exception as e:
        print("✗ Admin metrics error:", str(e))

# Test admin recent activity endpoint
def test_admin_activity(token):
    print("Testing admin recent activity endpoint...")
    url = "http://localhost:8000/api/admin/recent-activity"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            print("✓ Admin recent activity retrieved successfully")
            for activity in data:
                print(f"  {activity.get('date')}: {activity.get('action')} ({activity.get('time')})")
        else:
            print("✗ Admin recent activity failed with status code:", response.status_code)
    except Exception as e:
        print("✗ Admin recent activity error:", str(e))

# Test admin logout
def test_admin_logout(token):
    print("Testing admin logout...")
    url = "http://localhost:8000/api/admin/logout"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.post(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                print("✓ Admin logout successful")
            else:
                print("✗ Admin logout failed:", data.get("message"))
        else:
            print("✗ Admin logout failed with status code:", response.status_code)
    except Exception as e:
        print("✗ Admin logout error:", str(e))

if __name__ == "__main__":
    print("=== Admin Dashboard Test ===")
    
    # Test admin login
    token = test_admin_login()
    
    if token:
        # Test admin endpoints
        test_admin_metrics(token)
        test_admin_activity(token)
        test_admin_logout(token)
    
    print("=== Test Complete ===")