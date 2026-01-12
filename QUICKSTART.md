# Quick Start Guide - DeepFit

## 🚀 Get Started in 5 Minutes

### Step 1: Install Dependencies (2 minutes)
```bash
cd HeightAndWeightCalculator
pip install -r requirements.txt
```

### Step 2: Configure MongoDB Atlas (2 minutes)
1. Go to https://cloud.mongodb.com/ and create free account
2. Create cluster named `sih2573`
3. Get connection string
4. Create file `Backend/.env`:
```
MONGODB_URI=mongodb+srv://username:password@cluster.mongodb.net/?retryWrites=true&w=majority
DB_NAME=sih2573
```

### Step 3: Run Application (1 minute)
```bash
cd Backend
python app.py
```

Open browser: http://localhost:5000

## ✅ Verify Installation

You should see:
```
✅ Athlete data loaded successfully
✅ MongoDB connected successfully
 * Running on http://127.0.0.1:5000
```

## 🎯 First Steps

1. **Sign Up**: Create your account
2. **Login**: Access dashboard
3. **Try Exercise**: Start with Situps
4. **View Results**: Check performance dashboard

## 📞 Need Help?

- Check README.md for detailed documentation
- Verify .env file exists in Backend folder
- Ensure MongoDB Atlas IP whitelist includes your IP
- Check console for error messages

---

**Ready to use!** 🎉
