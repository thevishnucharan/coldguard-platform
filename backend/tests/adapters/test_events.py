import pytest
import asyncio
from app.adapters.events import LocalEventPublisher, LocalEventConsumer

@pytest.mark.asyncio
async def test_local_pub_sub():
    queue = asyncio.Queue()
    publisher = LocalEventPublisher(queue)
    consumer = LocalEventConsumer(queue)
    
    events_received = []
    
    def mock_callback(events):
        events_received.extend(events)
        
    await consumer.start_consuming(mock_callback)
    
    test_events = [{"temp": 5.0}, {"temp": 6.5}]
    await publisher.publish(test_events)
    
    # Wait briefly for async consumer to pick it up
    await asyncio.sleep(0.1)
    
    assert len(events_received) == 2
    assert events_received[0]["temp"] == 5.0
    assert events_received[1]["temp"] == 6.5
    
    await consumer.stop()
