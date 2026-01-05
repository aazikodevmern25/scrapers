from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()
client = MongoClient(os.getenv('MONGO_URI'))
db = client[os.getenv('MONGO_DB', 'Dhruval')]

# Get sample of HS codes from the screenshot
test_codes = ["390242", "390249", "390311", "390319", "390320", "390330", 
              "390410", "390420", "390430", "390441", "390450", "390461"]

print("\n" + "=" * 70)
print("CHECKING YOUR SUBMITTED HS CODES IN DATABASE:")
print("=" * 70)

already_exist = []
not_exist = []

for code in test_codes:
    count = db.trademap.count_documents({"HsCode": code})
    if count > 0:
        already_exist.append(code)
        records = list(db.trademap.find({"HsCode": code}, 
                                        {"Data.Country1": 1, "Data.Country2": 1}).limit(3))
        print(f"\n✅ HS {code}: {count} records ALREADY EXIST")
        print(f"   Sample countries:")
        for r in records[:3]:
            print(f"     - {r['Data']['Country1']} → {r['Data']['Country2']}")
    else:
        not_exist.append(code)
        print(f"\n❌ HS {code}: NOT in database (would be NEW)")

print("\n" + "=" * 70)
print("SUMMARY:")
print("=" * 70)
print(f"Codes already in database: {len(already_exist)} / {len(test_codes)}")
print(f"Codes NOT in database: {len(not_exist)} / {len(test_codes)}")
print(f"\nTotal database records: {db.trademap.count_documents({})}")
print("=" * 70)

if len(already_exist) == len(test_codes):
    print("\n⚠️  ALL YOUR HS CODES ALREADY EXIST IN DATABASE!")
    print("   That's why count is not increasing - they're being UPDATED")
    print("   To see new records, submit HS codes you haven't scraped before")
