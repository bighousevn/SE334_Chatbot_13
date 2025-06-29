from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.types import DomainDict
from rasa_sdk.events import UserUtteranceReverted, EventType
from rasa_sdk.events import SlotSet
from pymongo import MongoClient


MENU = {
    "phở bò": 50000,
    "cơm gà": 60000,
    "bánh mì": 30000,
    "trà sữa": 40000,
    "gỏi cuốn": 20000,
    "bún chả": 55000
}

class ActionShowMenu(Action):
    def name(self) -> Text:
        return "action_show_menu"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: DomainDict) -> List[Dict[Text, Any]]:
        # Kết nối MongoDB để lấy menu động
        client = MongoClient("mongodb://localhost:27017")
        db = client["chatbot"]
        foods = db["foods"].find({"available": True})

        menu_items = []
        for food in foods:
            menu_items.append(f"- {food['name']}: {food['price']}₫")
        if menu_items:
            dispatcher.utter_message(text="Menu hôm nay:\n" + "\n".join(menu_items))
        else:
            dispatcher.utter_message(text="Hiện chưa có món nào trong menu.")
        client.close()
        return []


class ActionAddToOrder(Action):
    def name(self) -> str:
        return "action_add_to_order"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: dict) -> list:
        import logging
        logging.debug(f"Running action_add_to_order: order_list={tracker.get_slot('order_list')}, dish={tracker.get_slot('dish')}, quantity={tracker.get_slot('quantity')}, entities={tracker.latest_message.get('entities', [])}")

        # Get latest entities first
        entities = tracker.latest_message.get("entities", [])
        latest_dish = next((e["value"] for e in entities if e["entity"] == "dish"), None)
        latest_quantity = next((e["value"] for e in entities if e["entity"] == "quantity"), None)

        # Get slots
        dish = latest_dish or tracker.get_slot("dish")
        quantity = latest_quantity or tracker.get_slot("quantity")
        order_list = tracker.get_slot("order_list") or []

        # If we have both dish and quantity
        if dish and quantity:
            try:
                quantity_val = int(quantity)
                dish_name = dish.lower()
                
                if dish_name in MENU:
                    price = MENU[dish_name]
                    order_item = {
                        "dish": dish,
                        "quantity": quantity_val,
                        "price": price
                    }
                    order_list.append(order_item)
                    dispatcher.utter_message(text=f"Đã thêm {quantity_val} phần {dish} vào đơn hàng.")
                    return [
                        SlotSet("order_list", order_list),
                        SlotSet("dish", None),
                        SlotSet("quantity", None)
                    ]
                else:
                    dispatcher.utter_message(text=f"Xin lỗi, chúng tôi không có món '{dish}'.")
                    return [SlotSet("dish", None)]
            except (ValueError, TypeError):
                dispatcher.utter_message(text=f"Số lượng '{quantity}' không hợp lệ.")
                return [SlotSet("quantity", None)]
        
        # If only dish is present
        elif dish:
            return [
                SlotSet("dish", dish),
                SlotSet("quantity", None)
            ]
        
        return []

class ActionShowOrder(Action):
    def name(self) -> str:
        return "action_show_order"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: dict) -> list:
        order_list = tracker.get_slot("order_list") or []
        if not order_list:
            dispatcher.utter_message(text="Bạn chưa đặt món nào.")
            return []

        summary = []
        total = 0
        for item in order_list:
            # Số lượng trong order_list giờ đã là một con số
            try:
                quantity = int(item["quantity"])
            except (ValueError, TypeError, KeyError):
                continue # Bỏ qua các mục bị lỗi trong giỏ hàng

            price = item["price"]
            line_total = quantity * price
            summary.append(f"- {quantity} x {item['dish']}: {line_total}₫")
            total += line_total

        summary_text = "\n".join(summary)
        dispatcher.utter_message(text=f"Đơn hàng của bạn:\n{summary_text}\nTổng cộng: {total}₫\nBạn có muốn xác nhận không?")
        return []

class ActionExecuteOrder(Action):
    def name(self) -> Text:
        return "action_execute_order"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: DomainDict) -> List[Dict[Text, Any]]:

        order_list = tracker.get_slot("order_list") or []
        if not order_list:
            dispatcher.utter_message(text="Không có đơn hàng để xác nhận.")
            return []

        dispatcher.utter_message(text="Đơn hàng của bạn đã được xác nhận! Cảm ơn bạn.")

        return [SlotSet("order_list", []), SlotSet("dish", None), SlotSet("quantity", None), SlotSet("fallback_count", 0)]


class ActionCancelOrder(Action):
    def name(self) -> Text:
        return "action_cancel_order"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: DomainDict) -> List[Dict[Text, Any]]:

        dispatcher.utter_message(text="Đơn hàng của bạn đã được hủy.")
        return [SlotSet("order_list", []), SlotSet("dish", None), SlotSet("quantity", None), SlotSet("fallback_count", 0)]
    

class ActionDefaultFallback(Action):
    def name(self) -> str:
        return "action_default_fallback"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: dict) -> list[EventType]:
        fallback_count = tracker.get_slot("fallback_count") or 0

        if fallback_count >= 3:
            dispatcher.utter_message(text="Tôi vẫn chưa hiểu bạn. Vui lòng thử lại sau.")
            return [UserUtteranceReverted(), SlotSet("fallback_count", 0)]  # Reset fallback_count
        else:
            # Check if intent is order_food_specific with valid entities
            intent = tracker.latest_message.get("intent", {}).get("name")
            entities = tracker.latest_message.get("entities", [])
            if intent == "order_food_specific" and any(e["entity"] in ["dish", "quantity"] for e in entities):
                # Skip fallback entirely
                return []
            
            dispatcher.utter_message(text="Xin lỗi, tôi chưa hiểu ý bạn. Bạn có thể nói lại không?")
            return [SlotSet("fallback_count", fallback_count + 1)]

class ActionAskQuantity(Action):
    def name(self):
        return "action_ask_quantity"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: dict):
        dish = tracker.get_slot("dish")
        if dish:
            dispatcher.utter_message(text=f"Bạn muốn gọi bao nhiêu phần {dish}?")
        return []

class ActionRestart(Action):
    def name(self) -> Text:
        return "action_restart"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: DomainDict) -> List[Dict[Text, Any]]:
        return [SlotSet("order_list", []), SlotSet("dish", None), SlotSet("quantity", None), SlotSet("fallback_count", 0)]

class ActionYouAreWelcome(Action):
    def name(self) -> Text:
        return "utter_you_are_welcome"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: DomainDict) -> List[Dict[Text, Any]]:
        dispatcher.utter_message(text="Không có gì, rất hân hạnh được phục vụ bạn!")
        return []

class ActionAskOpeningHours(Action):
    def name(self) -> Text:
        return "utter_ask_opening_hours"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: DomainDict) -> List[Dict[Text, Any]]:
        dispatcher.utter_message(text="Nhà hàng mở cửa từ 7h sáng đến 10h tối mỗi ngày.")
        return []

class ActionAskPromotion(Action):
    def name(self) -> Text:
        return "utter_ask_promotion"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: DomainDict) -> List[Dict[Text, Any]]:
        dispatcher.utter_message(text="Hôm nay có khuyến mãi: Giảm 10% cho đơn hàng trên 200.000đ!")
        return []
