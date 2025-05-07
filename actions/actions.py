

from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.types import DomainDict
from rasa_sdk.events import UserUtteranceReverted, EventType
from rasa_sdk.events import SlotSet

# Giả sử chúng ta có một cơ sở dữ liệu menu đơn giản dạng dict
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

        menu_items = "\n".join([f"- {dish}: {price}₫" for dish, price in MENU.items()])
        dispatcher.utter_message(text=f"Đây là menu của chúng tôi:\n{menu_items}")
        return []




class ActionAddToOrder(Action):
    def name(self) -> str:
        return "action_add_to_order"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: dict) -> list:
        # Lấy slot từ tracker
        dish = tracker.get_slot("dish")
        quantity = tracker.get_slot("quantity")
        order_list = tracker.get_slot("order_list") or []

        # Dự phòng: Trích xuất trực tiếp từ entity nếu slot là None
        if not dish or not quantity:
            entities = tracker.latest_message.get("entities", [])
            dish = dish or next((e["value"] for e in entities if e["entity"] == "dish"), None)
            quantity = quantity or next((e["value"] for e in entities if e["entity"] == "quantity"), None)

        if dish and quantity:
           if dish in MENU:
                price = MENU[dish]
                order_item = {
                    "dish": dish,
                    "quantity": quantity,
                    "price": price
                }
                order_list.append(order_item)
                dispatcher.utter_message(text=f"Đã thêm {order_item['dish']} vào đơn hàng.")
                return [SlotSet("order_list", order_list)]
        elif dish:
            dispatcher.utter_message(text="Bạn muốn gọi bao nhiêu phần?")
            return []
        else:
            dispatcher.utter_message(text="Bạn muốn đặt món gì?")
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
            # Lấy số lượng từ chuỗi "1 phần" -> 1
            quantity = int(item["quantity"].split()[0])  # Giả sử quantity có dạng "1 phần"
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

        # Ở đây có thể thêm logic lưu đơn vào database
        dispatcher.utter_message(text="Đơn hàng của bạn đã được xác nhận! Cảm ơn bạn.")

        # Xóa slot order_list
        return [{"event": "slot", "name": "order_list", "value": []}]


class ActionCancelOrder(Action):
    def name(self) -> Text:
        return "action_cancel_order"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: DomainDict) -> List[Dict[Text, Any]]:

        dispatcher.utter_message(text="Đơn hàng của bạn đã được hủy.")
        return [{"event": "slot", "name": "order_list", "value": []}]
    


class ActionDefaultFallback(Action):
    def name(self) -> str:
        return "action_default_fallback"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: dict) -> list[EventType]:
        # Lấy số lần fallback đã xảy ra từ slot
        fallback_count = tracker.get_slot("fallback_count") or 0

        # Kiểm tra số lần fallback tối đa
        if fallback_count >= 3:
            # Nếu số lần fallback đạt tối đa, dừng vòng lặp và thông báo cho người dùng
            dispatcher.utter_message(text="Tôi vẫn chưa hiểu bạn. Vui lòng thử lại sau.")
            return [UserUtteranceReverted()]  # Dừng vòng lặp

        # Nếu chưa đạt số lần tối đa, yêu cầu người dùng thử lại
        dispatcher.utter_message(text="Xin lỗi, tôi chưa hiểu ý bạn. Bạn có thể nói lại không?")
        
        # Tiếp tục chờ người dùng tương tác lại, không thực hiện hành động fallback thêm
        return [SlotSet("fallback_count", fallback_count + 1)]  # Tăng số lần fallback


class ActionAskQuantity(Action):
    def name(self):
        return "action_ask_quantity"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: dict):
       
        dish = tracker.get_slot("dish")

        if dish:
            message = f"Bạn muốn gọi bao nhiêu phần {dish} ạ?"
        else:
            message = "Bạn muốn gọi món gì ạ?"

        dispatcher.utter_message(text=message)
        return []
    

