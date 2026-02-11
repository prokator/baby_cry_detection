from baby_cry_detection.monitor.recipient_store import TelegramRecipientStore


def test_store_add_and_list(tmp_path):
    store = TelegramRecipientStore(str(tmp_path / "recipients.json"))
    store.add_chat_id("1")
    store.add_chat_id("2")
    store.add_chat_id("1")
    assert store.list_chat_ids() == ["1", "2"]
