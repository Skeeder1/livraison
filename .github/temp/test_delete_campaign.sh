#!/bin/bash

# Test delete campaign endpoint
echo "Testing DELETE campaign endpoint..."
echo ""

# First, get a test token (use curl to login)
echo "1. Creating test account..."
response=$(curl -s -X POST http://localhost:8000/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test_delete_'$(date +%s)'@example.com",
    "password": "TestPassword123!"
  }')

echo "Register response: $response"
token=$(echo "$response" | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)

if [ -z "$token" ]; then
  echo "Failed to get token"
  exit 1
fi

echo "Token: $token"
echo ""

# List campaigns to get one to delete
echo "2. Listing campaigns..."
campaigns=$(curl -s -X GET http://localhost:8000/v1/campaigns \
  -H "Authorization: Bearer $token")

echo "Campaigns response: $campaigns"
echo ""

# Extract campaign ID (if any exist)
campaign_id=$(echo "$campaigns" | grep -o '"id":"[^"]*' | head -1 | cut -d'"' -f4)

if [ -z "$campaign_id" ]; then
  echo "No campaigns found to test delete"
  exit 0
fi

echo "3. Testing DELETE endpoint with campaign ID: $campaign_id"
delete_response=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X DELETE http://localhost:8000/v1/campaigns/$campaign_id \
  -H "Authorization: Bearer $token")

echo "Delete response:"
echo "$delete_response"

# Extract HTTP code
http_code=$(echo "$delete_response" | grep "HTTP_CODE:" | cut -d':' -f2)
echo ""
echo "HTTP Status Code: $http_code"

if [ "$http_code" == "204" ]; then
  echo "✓ Delete endpoint works correctly (204 No Content)"
else
  echo "✗ Delete endpoint returned unexpected status code: $http_code"
fi
