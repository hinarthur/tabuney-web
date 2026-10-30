from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Msg
from member.models import Member
from django.contrib.auth.models import User

class FeedbackView(APIView):
    def post(self, request):
        email = request.data.get('email')
        guest_name = request.data.get('guest_name')
        content = request.data.get('content')

        if not content:
            return Response({'error': 'Content is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            msg_data = {'content': content}

            # 檢查是否為已登入用戶 (有 email 且能找到對應的 Member)
            if email:
                try:
                    user = User.objects.get(email=email)
                    member = Member.objects.get(id=user)
                    msg_data['sender'] = member
                except (User.DoesNotExist, Member.DoesNotExist):
                    return Response({'error': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)
            else:
                # 訪客留言，儲存 guest_name
                if not guest_name:
                    return Response({'error': 'Name or email is required for guests.'}, status=status.HTTP_400_BAD_REQUEST)
                msg_data['guest_name'] = guest_name

            # 設置 recipient 為 username="info" 的 Member
            try:
                info_user = User.objects.get(username="info")
                info_member = Member.objects.get(id=info_user)
                msg_data['recipient'] = info_member
            except (User.DoesNotExist, Member.DoesNotExist):
                return Response({'error': 'Recipient account "info" not found.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # 創建 Msg 記錄
            Msg.objects.create(**msg_data)
            return Response({'message': 'Feedback submitted successfully.'}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)