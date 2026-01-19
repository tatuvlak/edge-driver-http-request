# TV App Launcher - SmartThings Integration

Complete solution for launching Samsung TV apps through SmartThings routines.

## What's Included

- ✅ **SmartThings Edge Driver** - Runs on your SmartThings Hub
- ✅ **Python API Service** - Runs on QNAP NAS as Docker container
- ✅ **Docker Support** - Easy deployment with docker-compose
- ✅ **PAT Authentication** - For quick testing
- ✅ **OAuth Ready** - Production-ready authentication flow
- ✅ **Test Scripts** - Validate your setup

## Quick Links

- **[Quick Start Guide](QUICKSTART.md)** - Get running in 5 steps
- **[Full Documentation](README.md)** - Detailed setup and troubleshooting
- **[Test Scripts](scripts/)** - API testing tools

## Project Structure

```
edge-driver-http-request/
├── edge-driver/          # SmartThings Edge Driver (Lua)
│   ├── src/             # Driver source code
│   ├── config/          # Driver configuration
│   └── profiles/        # Device profiles
│
├── python-utility/       # Python API service
│   ├── app.py           # Flask application
│   ├── Dockerfile       # Docker image
│   ├── docker-compose.yml
│   └── requirements.txt
│
├── scripts/             # Helper scripts
│   ├── test-api.sh      # Bash test script
│   └── test-api.ps1     # PowerShell test script
│
├── README.md            # Full documentation
├── QUICKSTART.md        # Quick start guide
└── .gitignore
```

## How It Works

1. **SmartThings Routine** triggers the Edge Driver device
2. **Edge Driver** sends HTTP request to Python utility on QNAP
3. **Python Utility** calls SmartThings API to launch TV app
4. **TV** turns on and launches your weather app

## Requirements

- SmartThings Hub (v2 or v3)
- QNAP NAS with Container Station
- Samsung Smart TV (2016 or newer)
- SmartThings account
- Your Tizen app deployed to TV

## Next Steps

1. Read [QUICKSTART.md](QUICKSTART.md) for 5-step setup
2. Configure your `.env` file with credentials
3. Deploy Python utility to QNAP
4. Install Edge driver to SmartThings Hub
5. Test and create routine!

## Support

- SmartThings Community: https://community.smartthings.com/
- SmartThings Developer: https://developer.smartthings.com/

---

Made for controlling Samsung TV weather app via SmartThings routines 🌤️📺
