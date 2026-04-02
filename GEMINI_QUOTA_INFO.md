🚨 GEMINI API QUOTA EXCEEDED

CURRENT STATUS:
- API Key: Valid ✅
- API Endpoint: Working ✅
- Authentication: Successful ✅
- ❌ PROBLEM: Free tier quota exhausted (limit: 0 requests remaining)

ROOT CAUSE:
Your free tier quota for Gemini 2.0 Flash has been exceeded.

Google Gemini Free Tier Limits:
├─ Requests per minute (RPM): 15
├─ Requests per day (RPD): 1,000
├─ Input tokens per minute: 1,000,000
└─ Status: RESOURCE_EXHAUSTED

SOLUTIONS:

Option 1: Wait for Quota Reset ⏳
- Free tier quota resets daily at midnight UTC
- Retry after 38+ seconds shown in error message
- ⚠️  This is temporary - quota will exhaust again with heavy usage

Option 2: Switch to Different Model 🔄
Edit toaster/coils/gemini.py and change:
  FROM: "gemini-2.0-flash"
  TO:   "gemini-1.5-flash"  (better free tier limits)
  OR:   "gemini-1.5-pro"    (better for complex tasks)

Option 3: Upgrade to Paid Plan 💳
1. Go to https://ai.google.dev/pricing
2. Enable billing in Google Cloud Project
3. Upgrade to paid tier for unlimited access
4. No code changes needed - same API key works

Option 4: Disable AI Features 🤐
If you don't need AI responses, disable them:
- Set "notify_on_boot": false in config/bot_config.json
- Remove AI response handlers from toast.py
- Commands still work normally

RECOMMENDED:
For testing/hobby use: Use gemini-1.5-flash model
For production: Upgrade to paid plan (~$0.075 per million input tokens)

For more info:
- Quotas: https://ai.google.dev/gemini-api/docs/rate-limits
- Pricing: https://ai.google.dev/pricing
- Monitoring: https://ai.dev/rate-limit
