#!/bin/bash

# Real-time Progress Monitor
# Shows document count every 30 seconds

echo "=========================================="
echo "  Real-Time Progress Monitor"
echo "  Press Ctrl+C to stop"
echo "=========================================="
echo ""

PREVIOUS_COUNT=0

while true; do
    CURRENT_COUNT=$(mongosh "mongodb://admin:Aaziko%21%40%23123@202.47.115.6:27017/Dhruval?authSource=admin" --quiet --eval "db.trademap.countDocuments()" 2>/dev/null)
    
    if [ ! -z "$CURRENT_COUNT" ]; then
        TIMESTAMP=$(date "+%H:%M:%S")
        
        if [ "$PREVIOUS_COUNT" -eq 0 ]; then
            PREVIOUS_COUNT=$CURRENT_COUNT
        fi
        
        CHANGE=$((CURRENT_COUNT - PREVIOUS_COUNT))
        
        echo "[$TIMESTAMP] Documents: $CURRENT_COUNT | Change: +$CHANGE | Progress: $(echo "scale=2; ($CURRENT_COUNT / 8904) * 100" | bc)%"
        
        PREVIOUS_COUNT=$CURRENT_COUNT
    else
        echo "Error connecting to MongoDB"
    fi
    
    sleep 30
done
