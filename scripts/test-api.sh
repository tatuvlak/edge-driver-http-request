#!/bin/bash

# Configuration
BASE_URL="http://localhost:5000"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}=== TV App Launcher API Tests ===${NC}\n"

# Test 1: Health Check
echo -e "${GREEN}[1/4] Testing health endpoint...${NC}"
response=$(curl -s -w "\nHTTP_CODE:%{http_code}" "$BASE_URL/health")
http_code=$(echo "$response" | grep HTTP_CODE | cut -d':' -f2)
body=$(echo "$response" | grep -v HTTP_CODE)

if [ "$http_code" = "200" ]; then
    echo -e "${GREEN}✓ Health check passed${NC}"
    echo "$body" | python3 -m json.tool 2>/dev/null || echo "$body"
else
    echo -e "${RED}✗ Health check failed (HTTP $http_code)${NC}"
fi
echo ""

# Test 2: Config Check
echo -e "${GREEN}[2/4] Testing config endpoint...${NC}"
response=$(curl -s -w "\nHTTP_CODE:%{http_code}" "$BASE_URL/config")
http_code=$(echo "$response" | grep HTTP_CODE | cut -d':' -f2)
body=$(echo "$response" | grep -v HTTP_CODE)

if [ "$http_code" = "200" ]; then
    echo -e "${GREEN}✓ Config check passed${NC}"
    echo "$body" | python3 -m json.tool 2>/dev/null || echo "$body"
else
    echo -e "${RED}✗ Config check failed (HTTP $http_code)${NC}"
fi
echo ""

# Test 3: Launch App
echo -e "${GREEN}[3/4] Testing launch TV app endpoint...${NC}"
response=$(curl -s -w "\nHTTP_CODE:%{http_code}" \
    -X POST "$BASE_URL/launch-tv-app" \
    -H "Content-Type: application/json" \
    -d '{"action": "launch", "device_id": "test"}')
http_code=$(echo "$response" | grep HTTP_CODE | cut -d':' -f2)
body=$(echo "$response" | grep -v HTTP_CODE)

if [ "$http_code" = "200" ]; then
    echo -e "${GREEN}✓ Launch app request successful${NC}"
    echo "$body" | python3 -m json.tool 2>/dev/null || echo "$body"
else
    echo -e "${YELLOW}⚠ Launch app request returned HTTP $http_code (may be expected if TV is off)${NC}"
    echo "$body" | python3 -m json.tool 2>/dev/null || echo "$body"
fi
echo ""

# Test 4: Device Status
echo -e "${GREEN}[4/4] Testing device status endpoint...${NC}"
response=$(curl -s -w "\nHTTP_CODE:%{http_code}" "$BASE_URL/device-status")
http_code=$(echo "$response" | grep HTTP_CODE | cut -d':' -f2)
body=$(echo "$response" | grep -v HTTP_CODE)

if [ "$http_code" = "200" ]; then
    echo -e "${GREEN}✓ Device status check passed${NC}"
    echo "$body" | python3 -m json.tool 2>/dev/null || echo "$body"
else
    echo -e "${YELLOW}⚠ Device status check returned HTTP $http_code${NC}"
    echo "$body" | python3 -m json.tool 2>/dev/null || echo "$body"
fi
echo ""

echo -e "${YELLOW}=== Tests Complete ===${NC}"
