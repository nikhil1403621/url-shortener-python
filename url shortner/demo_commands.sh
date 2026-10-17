#!/usr/bin/env bash
# ==============================================================================
# Capstone Assignment — URL Shortener: Automated Demo & Terminal Commands Script
# ==============================================================================
set -e

# Colors for terminal output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

pause() {
  echo -e "\n${YELLOW}Press [Enter] to continue to the next step...${NC}"
  read -r
}

echo -e "${BLUE}================================================================${NC}"
echo -e "${BLUE}      CAPSTONE ASSIGNMENT: FULL TERMINAL DEMONSTRATION          ${NC}"
echo -e "${BLUE}================================================================${NC}"

# ------------------------------------------------------------------------------
# STEP 1: Healthcheck
# ------------------------------------------------------------------------------
echo -e "\n${GREEN}[STEP 1/5] Checking /health endpoint on localhost:8080...${NC}"
echo -e "Command: ${YELLOW}curl -s http://localhost:8080/health${NC}"
curl -s http://localhost:8080/health
echo ""
pause

# ------------------------------------------------------------------------------
# STEP 2: Full CRUD Lifecycle
# ------------------------------------------------------------------------------
echo -e "\n${GREEN}[STEP 2/5] Demonstrating CRUD Lifecycle via API + PostgreSQL...${NC}"

echo -e "\n${BLUE}--> 2A. CREATE Link (POST /shorten with custom code 'mycup')${NC}"
echo -e "Command: ${YELLOW}curl -i -X POST http://localhost:8080/shorten -H 'Content-Type: application/json' -d '{\"url\":\"https://example.com/demo-test\",\"custom\":\"mycup\"}'${NC}"
curl -i -X POST http://localhost:8080/shorten \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com/demo-test","custom":"mycup"}'

echo -e "\n${BLUE}--> 2B. READ / Follow Redirect (GET /mycup -> returns 302)${NC}"
echo -e "Command: ${YELLOW}curl -i http://localhost:8080/mycup${NC}"
curl -i http://localhost:8080/mycup

echo -e "\n${BLUE}--> 2C. UPDATE Destination URL (PUT /api/links/mycup)${NC}"
echo -e "Command: ${YELLOW}curl -i -X PUT http://localhost:8080/api/links/mycup -H 'Content-Type: application/json' -d '{\"url\":\"https://example.com/demo-updated\"}'${NC}"
curl -i -X PUT http://localhost:8080/api/links/mycup \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com/demo-updated"}'

echo -e "\n${BLUE}--> 2D. VERIFY in PostgreSQL Database (via psql)${NC}"
echo -e "Command: ${YELLOW}docker exec url-shortener-postgres psql -U postgres -d url_shortener -c \"SELECT code, url FROM links WHERE code = 'mycup';\"${NC}"
docker exec url-shortener-postgres psql -U postgres -d url_shortener -c "SELECT code, url FROM links WHERE code = 'mycup';"

echo -e "\n${BLUE}--> 2E. DELETE Link (DELETE /api/links/mycup)${NC}"
echo -e "Command: ${YELLOW}curl -i -X DELETE http://localhost:8080/api/links/mycup${NC}"
curl -i -X DELETE http://localhost:8080/api/links/mycup

echo -e "\n${BLUE}--> 2F. VERIFY Deletion from PostgreSQL (must return 0 rows)${NC}"
echo -e "Command: ${YELLOW}docker exec url-shortener-postgres psql -U postgres -d url_shortener -c \"SELECT code, url FROM links WHERE code = 'mycup';\"${NC}"
docker exec url-shortener-postgres psql -U postgres -d url_shortener -c "SELECT code, url FROM links WHERE code = 'mycup';"

pause

# ------------------------------------------------------------------------------
# STEP 3: Active Links List & Analytics
# ------------------------------------------------------------------------------
echo -e "\n${GREEN}[STEP 3/5] Inspecting Link List and Stats Endpoint...${NC}"
echo -e "Command: ${YELLOW}curl -s http://localhost:8080/api/links${NC}"
curl -s http://localhost:8080/api/links
echo ""

echo -e "\nCommand: ${YELLOW}curl -s http://localhost:8080/api/links/welcome/stats${NC}"
curl -s http://localhost:8080/api/links/welcome/stats
echo ""
pause

# ------------------------------------------------------------------------------
# STEP 4: Git Branch Consistency
# ------------------------------------------------------------------------------
echo -e "\n${GREEN}[STEP 4/5] Checking Git Branch Consistency (git diff main staging prod)...${NC}"
echo -e "Command: ${YELLOW}git log --oneline --graph -n 8${NC}"
git log --oneline --graph -n 8 || true

echo -e "\nChecking diff between origin/main and origin/staging (should be empty after promotion):"
echo -e "Command: ${YELLOW}git diff origin/main origin/staging${NC}"
git diff origin/main origin/staging || true

echo -e "\nChecking diff between origin/staging and origin/prod (should be empty after promotion):"
echo -e "Command: ${YELLOW}git diff origin/staging origin/prod${NC}"
git diff origin/staging origin/prod || true
pause

# ------------------------------------------------------------------------------
# STEP 5: Kubernetes Namespaces & Rollout
# ------------------------------------------------------------------------------
echo -e "\n${GREEN}[STEP 5/5] Kubernetes Status (qa, stage, prod)...${NC}"
if command -v kubectl &> /dev/null && kubectl cluster-info &> /dev/null; then
  echo -e "Command: ${YELLOW}kubectl get pods -n qa${NC}"
  kubectl get pods -n qa || true

  echo -e "\n${YELLOW}Would you like to trigger a live rollout restart in QA? (y/n)${NC}"
  read -r run_k8s_rollout
  if [ "$run_k8s_rollout" = "y" ]; then
    echo -e "Command: ${YELLOW}kubectl rollout restart deployment/url-shortener-app -n qa${NC}"
    kubectl rollout restart deployment/url-shortener-app -n qa
    echo -e "Command: ${YELLOW}kubectl rollout status deployment/url-shortener-app -n qa${NC}"
    kubectl rollout status deployment/url-shortener-app -n qa
    echo -e "\nVerifying running pod image:"
    kubectl get pods -n qa -o jsonpath='{range .items[*]}{.spec.containers[*].image}{"\n"}{end}'
  fi
else
  echo -e "${YELLOW}Kubectl or cluster not reachable right now. Run ./k8s/rollout-demo.sh when cluster is active.${NC}"
fi

echo -e "\n${GREEN}================================================================${NC}"
echo -e "${GREEN}      ALL DEMO CHECKS & CRUD COMMANDS COMPLETED SUCCESSFULLY!   ${NC}"
echo -e "${GREEN}================================================================${NC}"
