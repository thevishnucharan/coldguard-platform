import asyncio
import logging
from typing import Protocol, List, Dict, Any, Callable
from app.core.config import settings

logger = logging.getLogger(__name__)

# --- Interfaces ---

class EventPublisher(Protocol):
    async def publish(self, events: List[Dict[str, Any]]) -> None:
        """Publishes a batch of events to the message broker."""
        ...

class EventConsumer(Protocol):
    async def start_consuming(self, callback_fn: Callable[[List[Dict[str, Any]]], None]) -> None:
        """Starts consuming events and triggers the callback for each batch."""
        ...
        
    async def stop(self) -> None:
        """Stops the consumer gracefully."""
        ...

# --- Local Implementation ---

class LocalEventPublisher:
    def __init__(self, queue: asyncio.Queue):
        self.queue = queue
        
    async def publish(self, events: List[Dict[str, Any]]) -> None:
        await self.queue.put(events)
        logger.debug(f"Local publisher queued {len(events)} events.")

class LocalEventConsumer:
    def __init__(self, queue: asyncio.Queue):
        self.queue = queue
        self._running = False
        self._task = None
        
    async def start_consuming(self, callback_fn: Callable[[List[Dict[str, Any]]], None]) -> None:
        self._running = True
        logger.info("Local event consumer started.")
        
        async def consume_loop():
            while self._running:
                try:
                    events = await self.queue.get()
                    # Execute callback (could be a sync function doing db work)
                    # We wrap it in run_in_executor to avoid blocking the event loop
                    await asyncio.get_event_loop().run_in_executor(None, callback_fn, events)
                    self.queue.task_done()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Error processing local event queue: {e}")
                    
        self._task = asyncio.create_task(consume_loop())
        
    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        logger.info("Local event consumer stopped.")

# --- Azure Event Hubs Implementation ---

class AzureEventHubPublisher:
    def __init__(self, connection_string: str, eventhub_name: str):
        from azure.eventhub.aio import EventHubProducerClient  # optional dependency
        self.client = EventHubProducerClient.from_connection_string(
            conn_str=connection_string,
            eventhub_name=eventhub_name
        )
        
    async def publish(self, events: List[Dict[str, Any]]) -> None:
        import json
        from azure.eventhub import EventData
        async with self.client:
            event_data_batch = await self.client.create_batch()
            for ev in events:
                event_data = EventData(json.dumps(ev))
                event_data_batch.add(event_data)
            await self.client.send_batch(event_data_batch)
            logger.debug(f"Azure publisher sent {len(events)} events.")

class AzureEventHubConsumer:
    def __init__(self, connection_string: str, eventhub_name: str, consumer_group: str):
        from azure.eventhub.aio import EventHubConsumerClient  # optional dependency
        self.client = EventHubConsumerClient.from_connection_string(
            conn_str=connection_string,
            consumer_group=consumer_group,
            eventhub_name=eventhub_name
        )
        self._task = None
        
    async def start_consuming(self, callback_fn: Callable[[List[Dict[str, Any]]], None]) -> None:
        logger.info("Azure event consumer started.")
        
        async def on_event(partition_context, event):
            import json
            try:
                # We expect a batch size of 1 here or multiple depending on sdk
                payload = json.loads(event.body_as_str(encoding='UTF-8'))
                # Call our callback synchronously via executor
                await asyncio.get_event_loop().run_in_executor(None, callback_fn, [payload])
                await partition_context.update_checkpoint(event)
            except Exception as e:
                logger.error(f"Error processing azure event: {e}")

        async def receive_loop():
            async with self.client:
                await self.client.receive(on_event=on_event, starting_position="-1")
                
        self._task = asyncio.create_task(receive_loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
        await self.client.close()
        logger.info("Azure event consumer stopped.")

# --- Dependency Injection ---

# For local mode, manage queue tied to the current running event loop
_local_queue = None
_local_publisher = None
_local_consumer = None

def _get_local_components():
    global _local_queue, _local_publisher, _local_consumer
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if _local_queue is None or getattr(_local_queue, "_loop", None) != current_loop:
        _local_queue = asyncio.Queue()
        _local_publisher = LocalEventPublisher(_local_queue)
        _local_consumer = LocalEventConsumer(_local_queue)
    return _local_publisher, _local_consumer

def get_event_publisher() -> EventPublisher:
    if settings.EVENT_BACKEND == "azure_event_hub":
        if not settings.AZURE_EVENT_HUB_CONNECTION_STRING or not settings.AZURE_EVENT_HUB_NAME:
            logger.warning("Azure Event Hub config missing. Falling back to Local.")
            pub, _ = _get_local_components()
            return pub
        return AzureEventHubPublisher(
            settings.AZURE_EVENT_HUB_CONNECTION_STRING, 
            settings.AZURE_EVENT_HUB_NAME
        )
    pub, _ = _get_local_components()
    return pub

def get_event_consumer() -> EventConsumer:
    if settings.EVENT_BACKEND == "azure_event_hub":
        if not settings.AZURE_EVENT_HUB_CONNECTION_STRING or not settings.AZURE_EVENT_HUB_NAME or not settings.AZURE_EVENT_HUB_CONSUMER_GROUP:
            logger.warning("Azure Event Hub config missing. Falling back to Local.")
            _, cons = _get_local_components()
            return cons
        return AzureEventHubConsumer(
            settings.AZURE_EVENT_HUB_CONNECTION_STRING, 
            settings.AZURE_EVENT_HUB_NAME,
            settings.AZURE_EVENT_HUB_CONSUMER_GROUP
        )
    _, cons = _get_local_components()
    return cons
